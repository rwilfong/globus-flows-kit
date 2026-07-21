# A simple script to ensure it's online! 
from globus_compute_sdk import Executor


ENDPOINT_ID = "530a71eb-e079-486f-b825-230fe4b739eb"


def test_job(x: int) -> dict:
    import os
    import socket

    return {
        "input": x,
        "output": x * 2,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }


def main() -> None:
    with Executor(endpoint_id=ENDPOINT_ID) as executor:
        future = executor.submit(test_job, 21)
        result = future.result()
        print(f"Task ID: {future.task_id}")
        print(f"Result: {result}")


if __name__ == "__main__":
    main()