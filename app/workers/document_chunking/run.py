from workers.worker_runner import WorkerRunner

if __name__ == "__main__":
    from workers.document_chunking.handler import DocumentChunkingHandler

    runner = WorkerRunner()
    runner.run(processor_cls=DocumentChunkingHandler)
