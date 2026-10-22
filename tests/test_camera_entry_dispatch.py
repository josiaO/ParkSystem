"""Camera callback -> accepted plate -> one receipt and one gate request.

Only model output and external devices are mocked. No camera/printer/gate is used.
"""
import asyncio
from contextlib import ExitStack, nullcontext
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Camera, Gate, ParkingSession, Receipt, Site
from app.config import Settings
from app.infrastructure.hardware.receipt_printers import SimulatedKioskPrinter
from app.services.gates import GateCommandResult
from app.services.dedup import native_callbacks, camera_events
from app.services.recognition_runtime import runtime


class CameraEntryDispatchTests(unittest.TestCase):
    def run_flow(self, mode):
        from app import api_main as api
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        session.add(Site(id=1,name='Test'))
        session.add(Gate(id=1,name='Entry',site_id=1))
        session.commit()
        camera=Camera(id=1,name='Test',ip_address='127.0.0.1',site_id=1,gate_id=1,
                      sdk_handle=7,recognition_mode=mode,lane_direction='ENTRY',adapter_id='hvx')
        session.add(camera);session.commit()
        image=BytesIO(); Image.new('RGB',(640,360)).save(image,format='JPEG'); jpeg=image.getvalue()
        event={'image_id':0,'capture_token':'capture-one','plate':'ABC123','score':.99,'have_vehicle':True,
               'bbox':{'x1':100,'y1':150,'x2':280,'y2':190}}
        hvx=AsyncMock()
        hvx.drain_events.return_value=[event]
        hvx.event_jpeg.return_value=jpeg;hvx.event_crop.return_value=b''
        native_callbacks._seen.clear();camera_events._seen.clear();runtime.reset()
        api._local_alpr_ticks.clear() if hasattr(api,'_local_alpr_ticks') else None
        steps=[]
        camera_read = Mock()
        reader_result={'ok':True,'backend':'fastalpr','best':{'plate':'XYZ789','confidence':.99,
                       'bbox':{'x1':100,'y1':150,'x2':280,'y2':190}},'plates':[]}
        def read(*args,**kwargs):
            steps.append('fastalpr');return reader_result
        async def open_gate(*args,**kwargs):
            self.assertEqual(len(list(session.scalars(select(Receipt)))),1)
            steps.append('gate');return GateCommandResult(True,True,'test','t')
        printer=SimulatedKioskPrinter()
        try:
            with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                for name,value in [('app.api_main.HVXHostClient',lambda:hvx),
                    ('app.api_main._show_camera_read',camera_read),
                    ('app.api_main.short_session',lambda:nullcontext(session)),
                    ('app.services.node_scope.camera_in_recognition_scope',lambda *a,**k:True),
                    ('app.services.modules.is_enabled',lambda *a,**k:True),
                    ('app.services.hybrid_fusion.routes_camera',lambda *a,**k:False),
                    ('app.recognition_worker.worker_owns_software_reads',lambda *a:False),
                    ('app.services.ai_review.schedule_capture_review',lambda *a,**k:None),
                    ('app.services.alpr.recognize_plate_crop_bytes',read),
                    ('app.services.alpr.recognize_arrival_bytes',read),
                    ('app.api_main._local_alpr_ready',lambda *a:True),
                    ('app.application.live_parking.receipt_printer_for',lambda *a:printer),
                    ('app.services.simulation._pulse_gate',open_gate)]:
                    stack.enter_context(patch(name,value))
                stack.enter_context(patch.object(Settings,'media_dir',new_callable=PropertyMock,return_value=Path(folder)))
                async def run():
                    await api._drain_camera_events(1,7)
                    await api._drain_camera_events(1,7)
                asyncio.run(run())
                hvx.event_jpeg.assert_awaited_once_with(7, capture_token="capture-one")
                hvx.event_crop.assert_awaited_once_with(7, capture_token="capture-one")
                rows=list(session.scalars(select(ParkingSession)))
                self.assertEqual(len(rows),1)
                self.assertEqual(len(list(session.scalars(select(Receipt)))),1)
                self.assertEqual(steps.count('gate'),1)
                if mode=='NATIVE_ONLY':
                    self.assertEqual(rows[0].plate,'ABC123')
                    self.assertEqual(steps,['gate'])
                else:
                    self.assertEqual(rows[0].plate,'XYZ789')
                    self.assertEqual(steps,['fastalpr','gate'])
                    self.assertEqual(camera_read.call_args.kwargs['plate'], '')
        finally:
            session.close();engine.dispose();runtime.reset()
            native_callbacks._seen.clear();camera_events._seen.clear()

    def test_native_callback_prints_and_dispatches_once(self):
        self.run_flow('NATIVE_ONLY')

    def test_fastalpr_decides_before_native_text_can_open_gate(self):
        self.run_flow('FASTALPR_ONLY')

    def test_chinese_no_plate_card_is_detected_on_the_panorama(self):
        from app import api_main as api
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        session.add(Site(id=1, name='Test'))
        session.add(Gate(id=1, name='Entry', site_id=1))
        session.commit()
        camera = Camera(id=1, name='Test', ip_address='127.0.0.1', site_id=1, gate_id=1,
                        sdk_handle=7, recognition_mode='FASTALPR_ONLY', lane_direction='ENTRY', adapter_id='hvx')
        session.add(camera)
        session.commit()
        scene = BytesIO()
        Image.new('RGB', (640, 360), (40, 40, 40)).save(scene, format='JPEG')
        card = BytesIO()
        Image.new('RGB', (320, 100), (20, 90, 210)).save(card, format='JPEG')
        event = {'image_id': 4, 'capture_token': 'no-plate', 'plate': '无车牌', 'score': 0.2, 'have_vehicle': True}
        hvx = AsyncMock()
        hvx.drain_events.return_value = [event]
        hvx.event_jpeg.return_value = scene.getvalue()
        hvx.event_crop.return_value = card.getvalue()
        native_callbacks._seen.clear()
        camera_events._seen.clear()
        runtime.reset()
        seen = {}

        def read_frame(jpeg, **kwargs):
            seen['frame'] = jpeg
            return {'ok': True, 'backend': 'fastalpr', 'best': {
                'plate': 'T285DQP', 'plate_normalized': 'T285DQP', 'confidence': 0.95,
                'bbox': {'x1': 100, 'y1': 200, 'x2': 280, 'y2': 240, 'image_width': 640, 'image_height': 360},
            }, 'plates': []}

        def read_crop(jpeg, **kwargs):
            seen['crop'] = jpeg
            return {'ok': True, 'backend': 'fastalpr', 'best': {
                'plate': 'T285DQP', 'plate_normalized': 'T285DQP', 'confidence': 0.95,
                'bbox': {'x1': 100, 'y1': 200, 'x2': 280, 'y2': 240, 'image_width': 640, 'image_height': 360},
            }, 'plates': []}

        try:
            with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                for name, value in [
                    ('app.api_main.HVXHostClient', lambda: hvx),
                    ('app.api_main.short_session', lambda: nullcontext(session)),
                    ('app.services.node_scope.camera_in_recognition_scope', lambda *a, **k: True),
                    ('app.services.modules.is_enabled', lambda *a, **k: True),
                    ('app.services.hybrid_fusion.routes_camera', lambda *a, **k: False),
                    ('app.recognition_worker.worker_owns_software_reads', lambda *a: False),
                    ('app.services.ai_review.schedule_capture_review', lambda *a, **k: None),
                    ('app.services.alpr.locate_plate_boxes', lambda *a, **k: ([{
                        'x1': 100, 'y1': 200, 'x2': 280, 'y2': 240, 'image_width': 640, 'image_height': 360,
                    }], {'available': True})),
                    ('app.api_main.recognize_frame', read_frame),
                    ('app.services.alpr.recognize_arrival_bytes', read_frame),
                    ('app.services.alpr.recognize_plate_crop_bytes', read_crop),
                    ('app.api_main._local_alpr_ready', lambda *a: True),
                    ('app.application.live_parking.receipt_printer_for', lambda *a: SimulatedKioskPrinter()),
                    ('app.services.simulation._pulse_gate', AsyncMock(return_value=GateCommandResult(True, True, 'test', 't'))),
                ]:
                    stack.enter_context(patch(name, value))
                stack.enter_context(patch.object(Settings, 'media_dir', new_callable=PropertyMock, return_value=Path(folder)))
                asyncio.run(api._drain_camera_events(1, 7))
            self.assertNotEqual(seen.get('crop'), card.getvalue())
            self.assertTrue(seen.get('crop', b'')[:2] == b'\xff\xd8' or seen.get('frame', b'')[:2] == b'\xff\xd8')
            plates = [row.plate for row in session.scalars(select(ParkingSession))]
            self.assertEqual(plates, ['T285DQP'])
        finally:
            session.close()
            engine.dispose()
            runtime.reset()
            native_callbacks._seen.clear()
            camera_events._seen.clear()

    def test_empty_lane_callback_is_not_captured(self):
        from app import api_main as api
        from app.services.preview import get_state, remember_last_car
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        session.add(Site(id=1, name='Test'))
        session.add(Gate(id=1, name='Entry', site_id=1))
        session.commit()
        session.add(Camera(id=1, name='Test', ip_address='127.0.0.1', site_id=1, gate_id=1,
                           sdk_handle=7, recognition_mode='FASTALPR_ONLY', lane_direction='ENTRY', adapter_id='hvx'))
        session.commit()
        scene = BytesIO()
        Image.new('RGB', (640, 360), (12, 12, 12)).save(scene, format='JPEG')
        event = {'image_id': 8, 'capture_token': 'empty', 'plate': '无车牌', 'score': 0, 'have_vehicle': True}
        hvx = AsyncMock()
        hvx.drain_events.return_value = [event]
        hvx.event_jpeg.return_value = scene.getvalue()
        hvx.event_crop.return_value = b''
        native_callbacks._seen.clear()
        camera_events._seen.clear()
        runtime.reset()
        remember_last_car(1, None)
        seen = {}
        try:
            with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                for name, value in [
                    ('app.api_main.HVXHostClient', lambda: hvx),
                    ('app.api_main.short_session', lambda: nullcontext(session)),
                    ('app.services.alpr.locate_plate_boxes', lambda *a, **k: ([], {'available': True})),
                    ('app.api_main.recognize_frame', lambda *a, **k: seen.setdefault('ocr', True)),
                ]:
                    stack.enter_context(patch(name, value))
                stack.enter_context(patch.object(Settings, 'media_dir', new_callable=PropertyMock, return_value=Path(folder)))
                asyncio.run(api._drain_camera_events(1, 7))
            self.assertNotIn('ocr', seen)
            self.assertFalse(list(session.scalars(select(ParkingSession))))
            self.assertIsNone((get_state(1).last_car or {}).get('snapshot_url'))
        finally:
            session.close()
            engine.dispose()
            runtime.reset()
            native_callbacks._seen.clear()
            camera_events._seen.clear()
