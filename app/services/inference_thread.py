"""Keep admission ownership until a cancelled native inference actually exits."""
import asyncio


async def run_inference(function, /, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Python cannot stop an ONNX thread. Releasing the lane now would
        # allow repeated timeouts to accumulate concurrent model executions.
        try:
            await task
        except Exception:
            pass
        raise
