# Corpus Display Policy

This policy defines the reader-facing category labels, variant labels, and default variant order. Stable `corpus_id`, `work_id`, `variant_id`, source paths, and citation URLs remain unchanged.

## Shared Rules

- Reader labels are Korean; scholarly edition sigla such as OSHB, SBLGNT, LXX, SKS, and IDP remain visible.
- A URL with an explicit `variant` always wins over the default.
- Default selection favors a complete readable text. Index and metadata variants remain available but are not selected ahead of full text.
- Canon labels describe this archive's source grouping and do not make theological claims about a universal canon.
- Policy is centralized in `corpora/display_policy.py`; builders keep source-facing metadata intact.

## Nietzsche

- Works have no interchangeable text variants in the current reader.
- Category labels distinguish major published works, the Untimely Meditations, late/posthumously edited works, and lectures/essays/fragments.
- Existing work sigla and citation anchors remain the primary stable identifiers.

## Bible

- `hebrew_bible`: **히브리어 성경**, displayed with the OSHB source label.
- `greek_nt`: **그리스어 신약성경**, displayed with the SBLGNT source label.
- `lxx_deuterocanon`: **칠십인역(LXX)·제2경전**, displayed with the Swete LXX source label.
- Old Testament direct references still prefer OSHB, New Testament references prefer SBLGNT, and an explicit `lxx` prefix selects LXX when available.

## Kierkegaard

Default order:

1. **본문** (`text`)
2. **주석** (`commentary`)
3. **텍스트 성립 자료** (`textual_account`)

The default is the primary text. Commentary and textual-account material are supporting variants and remain directly addressable.

## Wittgenstein

Default order:

1. **정규화 전사·전체** (`source_transcription_normalized.full`)
2. **정규화 전사·색인** (`source_transcription_normalized.index`)
3. **외교적 전사·전체** (`source_transcription_diplomatic.full`)
4. **외교적 전사·색인** (`source_transcription_diplomatic.index`)
5. **IDP 선형 전사** (`idp_transcription_linear`)
6. **IDP 외교적 전사** (`idp_transcription_diplomatic`)
7. **메타데이터** (`source_metadata`)

Normalized full transcription is the reading default where present. Diplomatic, IDP, index, and metadata representations remain available for source comparison and provenance work.

## Validation

Run:

```powershell
python .\scripts\check_layout_contracts.py
python .\scripts\check_api_contracts.py
python .\scripts\check_corpus_schema.py
```
