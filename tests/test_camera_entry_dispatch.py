"""Camera callback -> accepted plate -> one receipt and one gate request.

Only model output and external devices are mocked. No camera/printer/gate is used.
"""
import asyncio
from contextlib import ExitStack, nullcontext
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

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
        event={'image_id':123,'plate':'ABC123','score':.99,'have_vehicle':True,
               'bbox':{'x1':100,'y1':150,'x2':280,'y2':190}}
        hvx=AsyncMock()
        hvx.drain_events.return_value=[event]
        hvx.event_jpeg.return_value=jpeg;hvx.event_crop.return_value=b''
        native_callbacks._seen.clear();camera_events._seen.clear();runtime.reset()
        api._local_alpr_ticks.clear() if hasattr(api,'_local_alpr_ticks') else None
        steps=[]
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
                    ('app.api_main.short_session',lambda:nullcontext(session)),
                    ('app.services.node_scope.camera_in_recognition_scope',lambda *a,**k:True),
                    ('app.services.modules.is_enabled',lambda *a,**k:True),
                    ('app.services.hybrid_fusion.routes_camera',lambda *a,**k:False),
                    ('app.recognition_worker.worker_owns_software_reads',lambda *a:False),
                    ('app.services.ai_review.schedule_capture_review',lambda *a,**k:None),
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
        finally:
            session.close();engine.dispose();runtime.reset()
            native_callbacks._seen.clear();camera_events._seen.clear()

    def test_native_callback_prints_and_dispatches_once(self):
        self.run_flow('NATIVE_ONLY')

    def test_fastalpr_decides_before_native_text_can_open_gate(self):
        self.run_flow('FASTALPR_ONLY')
