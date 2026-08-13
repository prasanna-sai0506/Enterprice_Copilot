# How RAG works in this product

RAG = **Retrieval-Augmented Generation**.

The model is not allowed to invent company policy from the internet.
It may only answer using **chunks** retrieved from **that enterprise’s** documents.

```
Employee question
      │
      ▼
Embed the question (same MiniLM model used when files were uploaded)
      │
      ▼
Search Chroma collection  ns_<company>   WHERE tenant_id = this company
      │
      ▼
Keep chunks whose access_level the user may see
   (every employee always sees access_level = "general")
      │
      ▼
Re-rank: 65% vector similarity + 35% keyword overlap
      │
      ▼
Top 6 chunks + your question → Groq LLaMA
      │
      ▼
Answer + source file / page  (or “not in our knowledge base”)
```

## Chunking

A 20-page handbook is **not** stored as one blob.

1. Extract text (PDF page, Word paragraphs, Excel sheets, TXT).
2. Split on headings → blank lines → sentences.
3. Each piece is about **700 characters**, with **120 characters overlap**
   so a sentence that sits on the cut is still complete in one of the two chunks.
4. Tiny scraps under 40 characters are dropped.
5. Every piece is saved with: `tenant_id`, `doc_id`, `filename`, `page`, `access_level`.

Example: *“Earned leave: 20 days”* lives in its own chunk. Asking
“how many earned leave days?” matches that chunk, not the whole file.

## Isolation

Wipro’s collection is `ns_wipro`. Apex Forge is `ns_apexforge`.
A query **always** filters `tenant_id`. Company A never sees Company B.

`general` documents are visible to **all employees of that one company**.
HR-only / finance-only files stay scoped.
