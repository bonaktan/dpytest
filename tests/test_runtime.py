import asyncio

import pytest

from discord.ext.test.runtime import Runtime


@pytest.mark.asyncio
async def test_close_cancels_only_owned_work():
    first, second = Runtime(), Runtime()
    started = asyncio.Event()

    async def wait():
        started.set()
        await asyncio.Event().wait()

    owned = first.create_task(wait())
    other = second.create_task(wait())
    await started.wait()
    await first.close()
    assert owned.cancelled()
    assert not other.done()
    await second.close()


@pytest.mark.asyncio
async def test_errors_are_retained_and_new_work_rejected_after_close():
    runtime = Runtime()

    async def fail():
        raise ValueError("callback failed")

    task = runtime.create_task(fail())
    await asyncio.wait({task})
    await asyncio.sleep(0)  # allow done callbacks to run
    assert len(runtime.errors) == 1
    assert str(runtime.errors[0]) == "callback failed"
    await runtime.close()
    with pytest.raises(RuntimeError, match="closing"):
        runtime.create_task(fail())
