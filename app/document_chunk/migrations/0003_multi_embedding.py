from django.db import migrations, models
from pgvector.django import VectorField, HnswIndex


class Migration(migrations.Migration):

    dependencies = [
        ("document_chunk", "0002_documentchunk_bounding_polygons"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentchunk",
            name="section_type",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="section_title",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="context_prefix",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="embedding_title",
            field=VectorField(blank=True, dimensions=1024, null=True),
        ),
        migrations.AddField(
            model_name="documentchunk",
            name="embedding_doc",
            field=VectorField(blank=True, dimensions=1024, null=True),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=HnswIndex(
                name="chunk_embedding_title_hnsw",
                fields=["embedding_title"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=HnswIndex(
                name="chunk_embedding_doc_hnsw",
                fields=["embedding_doc"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
