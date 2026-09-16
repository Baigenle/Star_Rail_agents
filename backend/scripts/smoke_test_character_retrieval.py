from pathlib import Path

from app.rag.local_retriever import (
    document_quality_issues,
    load_character_documents,
    search_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = PROJECT_ROOT / "docs" / "hsr_nanoka_characters" / "characters"
QUERIES = (
    "黄泉是什么属性，命途是什么？",
    "三月七的战技护盾有什么效果？",
    "阮梅的技能和属性",
    "雷属性虚无角色",
)


def main() -> None:
    documents = load_character_documents(KNOWLEDGE_DIR)
    rejected = [document for document in documents if document_quality_issues(document)]
    print(
        f"loaded_documents={len(documents)} "
        f"searchable_documents={len(documents) - len(rejected)} rejected_documents={len(rejected)}"
    )
    for document in rejected:
        print(f"rejected={document.path.name} issues={document_quality_issues(document)}")
    for query in QUERIES:
        print(f"\nquery={query}")
        for result in search_documents(documents, query, limit=3):
            print(
                f"- {result.document.title} | score={result.score:.2f} | "
                f"version={result.document.metadata.get('data_version')} | "
                f"source={result.document.metadata.get('source_page')}"
            )
            print(f"  {result.snippet}")


if __name__ == "__main__":
    main()
