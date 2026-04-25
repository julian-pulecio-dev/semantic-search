from workers.worker_runner import WorkerRunner

if __name__ == "__main__":
    runner = WorkerRunner()
    from workers.document_chunking.handler import DocumentChunkingHandler
    runner.run(processor_cls=DocumentChunkingHandler)
