from workers.worker_runner import WorkerRunner

if __name__ == "__main__":
    from workers.embedding.handler import EmbeddingHandler

    runner = WorkerRunner()
    runner.run(processor_cls=EmbeddingHandler)
