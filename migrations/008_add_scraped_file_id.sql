-- Migration 008: Add scraped_file_id column to extractions and memo_extractions
-- Links extraction results back to the original scraped_files record for end-to-end traceability.

ALTER TABLE extractions
  ADD COLUMN scraped_file_id UUID REFERENCES scraped_files(id);
CREATE INDEX idx_extractions_scraped_file_id ON extractions(scraped_file_id);

ALTER TABLE memo_extractions
  ADD COLUMN scraped_file_id UUID REFERENCES scraped_files(id);
CREATE INDEX idx_memo_extractions_scraped_file_id ON memo_extractions(scraped_file_id);
