import httpx
try:
    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
    print("Success:", client)
except BaseException as e:
    import traceback
    traceback.print_exc()
