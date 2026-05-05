from workers.worker_runner import WorkerRunner

if __name__ == "__main__":
    runner = WorkerRunner()
    from workers.document_page_slicing.handler import (
        DocumentPageSlicingHandler,
    )

    runner.run(processor_cls=DocumentPageSlicingHandler)
