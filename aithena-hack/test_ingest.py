from app.ingest import ingest_file, chunk_document
import os

corpus_dir = "corpus"
all_files = [
    f for f in os.listdir(corpus_dir)
    if f.endswith((".pdf", ".docx", ".pptx", ".ppt"))
]

if not all_files:
    print("No supported files found in corpus/")
else:
    for filename in all_files:
        filepath = os.path.join(corpus_dir, filename)
        print(f"\n=== Testing: {filename} ===")

        try:
            result = ingest_file(filepath)

            print(f"File type : {result['file_type']}")
            print(f"Pages     : {len(result['pages'])}")
            print(f"Scanned   : {result['is_scanned']}")
            print(f"Clauses   : {result['clauses_total']}")
            print(f"Text      : {len(result['full_text'])} characters")

            if result.get("warning"):
                print(f"Warning   : {result['warning']}")

            for page in result["pages"]:
                ocr = " (OCR)" if page["is_ocr"] else ""
                img = " [has image]" if page["image_path"] else ""
                print(f"  Page {page['page_number']}{ocr}{img}: {len(page['blocks'])} blocks, {len(page['text'])} chars")

            chunks = chunk_document(result)
            print(f"Chunks    : {len(chunks)}")
            print("PASSED - OK")

        except ValueError as e:
            if "PASSWORD_PROTECTED" in str(e):
                print("BLOCKED - OK: Password protected PDF detected cleanly")
            else:
                print(f"ERROR: {e}")
        except Exception as e:
            print(f"CRASHED: {e}")