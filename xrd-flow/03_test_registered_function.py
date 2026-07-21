import time

from globus_compute_sdk import Executor


ENDPOINT_ID = "6f2a082f-5db5-401f-8c3d-65f6f5e8bba4"
FUNCTION_ID = "9bb612a8-d807-471b-8e1f-c008970aa7f3"
FILE_PATH = "/home/rwilfong/globus-flows/xrd-ex/xrd_scan_001.csv"


def main() -> None:
    with Executor(endpoint_id=ENDPOINT_ID) as executor:
        future = executor.submit_to_registered_function(
            FUNCTION_ID,
            kwargs={
                "file_path": FILE_PATH,
                "output_path": (
                    "/home/rwilfong/globus-flows/xrd-ex/work/"
                    "xrd_scan_001_results.json"
                ),
            },
        )

        print("Submitted")

        while not future.done():
            print("Waiting for result...")
            time.sleep(5)

        print("Task ID:", getattr(future, "task_id", None))
        print("Result:", future.result())


if __name__ == "__main__":
    main()