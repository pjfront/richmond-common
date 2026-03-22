-- Migration 046: Agenda item attachments table
-- Stores extracted text from eSCRIBE attachment PDFs (staff reports,
-- contracts, bid matrices) linked to their parent agenda item.
-- Enables attachment-informed summary generation (R1).

CREATE TABLE IF NOT EXISTS agenda_item_attachments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    document_id TEXT,                    -- eSCRIBE document ID
    filename TEXT NOT NULL,
    source_url TEXT,
    extracted_text TEXT,                 -- Full extracted text from PDF
    char_count INTEGER,                 -- Length of extracted_text for quick filtering
    mime_type TEXT DEFAULT 'application/pdf',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookup by agenda item
CREATE INDEX IF NOT EXISTS idx_aia_agenda_item_id
    ON agenda_item_attachments(agenda_item_id);

-- Index for dedup by document_id
CREATE INDEX IF NOT EXISTS idx_aia_document_id
    ON agenda_item_attachments(document_id);

COMMENT ON TABLE agenda_item_attachments IS
    'Extracted text from eSCRIBE agenda item attachments (staff reports, contracts). Fed into summary generation.';
