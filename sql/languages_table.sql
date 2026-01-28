-- Normalized languages table for South African official languages
-- Run this manually in Supabase SQL Editor when ready

CREATE TABLE languages (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) UNIQUE NOT NULL,
  iso_code VARCHAR(10) UNIQUE NOT NULL
);

INSERT INTO languages (name, iso_code) VALUES
  ('English', 'en'),
  ('Afrikaans', 'af'),
  ('IsiZulu', 'zu'),
  ('IsiXhosa', 'xh'),
  ('Sepedi', 'nso'),
  ('Setswana', 'tn'),
  ('Sesotho', 'st'),
  ('Xitsonga', 'ts'),
  ('SiSwati', 'ss'),
  ('Tshivenda', 've'),
  ('IsiNdebele', 'nr');

-- Add language_id FK to extractions table (run after creating languages table)
ALTER TABLE extractions ADD COLUMN language_id INTEGER REFERENCES languages(id);
