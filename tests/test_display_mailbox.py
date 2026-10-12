from app.desktop.frame_mailbox import DisplayMailbox


def test_slow_painter_has_one_notification_and_gets_latest_frame():
    box = DisplayMailbox()
    assert box.offer(b'first')
    for i in range(1000):
        assert not box.offer(str(i).encode())
    assert box.take() == b'999'
    assert box.offer(b'next')
    assert box.take() == b'next'
    assert box.take() is None


def test_live_callback_ignores_destroyed_and_replaced_streams():
    # Exercise the actual slot without requiring a Qt display on the test host.
    import ast
    from pathlib import Path
    from types import SimpleNamespace

    source = Path(__file__).resolve().parents[1] / 'app/desktop/main.py'
    tree = ast.parse(source.read_text())
    pane = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CameraLivePane')
    method = next(n for n in pane.body if isinstance(n, ast.FunctionDef) and n.name == '_consume_live_frame')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    consume = namespace['_consume_live_frame']
    painted = []
    view = SimpleNamespace(sender=lambda: None, _mjpeg=None, _queue_live_frame=painted.append)
    consume(view)
    old = SimpleNamespace(mailbox=DisplayMailbox())
    current = SimpleNamespace(mailbox=DisplayMailbox())
    old.mailbox.offer(b'old')
    current.mailbox.offer(b'current')
    view._mjpeg = current
    view.sender = lambda: old
    consume(view)
    assert painted == []
    view.sender = lambda: current
    consume(view)
    assert painted == [b'current']
