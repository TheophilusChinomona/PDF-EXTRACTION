-- Migration 011: Validation and extraction triggers (US-005, US-008)
-- Requires: CREATE EXTENSION IF NOT EXISTS pgmq;
-- On scraped_files.status -> 'downloaded': enqueue to validation_queue, set status = 'validating'
-- On validation_results.status -> 'correct': enqueue to extraction_queue, set scraped_files.status = 'queued_for_extraction'

-- ============================================================================
-- Ensure PGMQ extension and queues exist
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgmq;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pgmq.list_queues() WHERE queue_name = 'validation_queue') THEN
    PERFORM pgmq.create('validation_queue');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pgmq.list_queues() WHERE queue_name = 'extraction_queue') THEN
    PERFORM pgmq.create('extraction_queue');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pgmq.list_queues() WHERE queue_name = 'validation_dead_letter') THEN
    PERFORM pgmq.create('validation_dead_letter');
  END IF;
END $$;

-- ============================================================================
-- Trigger: scraped_files status -> 'downloaded'
-- ============================================================================

CREATE OR REPLACE FUNCTION trg_scraped_files_enqueue_validation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  storage_url_text TEXT;
  file_name_text TEXT;
  msg JSONB;
BEGIN
  IF NEW.status <> 'downloaded' THEN
    RETURN NEW;
  END IF;

  file_name_text := COALESCE(split_part(NEW.storage_path, '/', -1), '');
  storage_url_text := 'gs://' || COALESCE(NEW.storage_bucket, '') || '/' || COALESCE(TRIM(LEADING '/' FROM NEW.storage_path), '');

  msg := jsonb_build_object(
    'scraped_file_id', NEW.id,
    'storage_url', storage_url_text,
    'file_name', file_name_text,
    'triggered_at', now()
  );

  PERFORM pgmq.send('validation_queue', msg);

  UPDATE scraped_files SET status = 'validating' WHERE id = NEW.id;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS scraped_files_enqueue_validation ON scraped_files;
CREATE TRIGGER scraped_files_enqueue_validation
  AFTER UPDATE ON scraped_files
  FOR EACH ROW
  WHEN (NEW.status = 'downloaded')
  EXECUTE FUNCTION trg_scraped_files_enqueue_validation();

-- ============================================================================
-- Trigger: validation_results status -> 'correct'
-- ============================================================================

CREATE OR REPLACE FUNCTION trg_validation_results_enqueue_extraction()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  s scraped_files%ROWTYPE;
  storage_url_text TEXT;
  doc_type_text TEXT;
  meta JSONB;
  msg JSONB;
BEGIN
  IF NEW.status <> 'correct' THEN
    RETURN NEW;
  END IF;

  SELECT * INTO s FROM scraped_files WHERE id = NEW.scraped_file_id;
  IF NOT FOUND THEN
    RETURN NEW;
  END IF;

  storage_url_text := 'gs://' || COALESCE(s.storage_bucket, '') || '/' || COALESCE(TRIM(LEADING '/' FROM s.storage_path), '');
  doc_type_text := COALESCE(s.document_type, 'question_paper');

  meta := jsonb_build_object(
    'subject', COALESCE(NEW.subject, s.subject),
    'grade', COALESCE(NEW.grade::text, s.grade::text),
    'year', COALESCE(NEW.year, s.year::text),
    'session', s.session,
    'syllabus', COALESCE(NEW.syllabus, s.syllabus)
  );

  msg := jsonb_build_object(
    'scraped_file_id', NEW.scraped_file_id,
    'storage_url', storage_url_text,
    'document_type', doc_type_text,
    'metadata', meta
  );

  PERFORM pgmq.send('extraction_queue', msg);

  UPDATE scraped_files SET status = 'queued_for_extraction' WHERE id = NEW.scraped_file_id;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS validation_results_enqueue_extraction ON validation_results;
CREATE TRIGGER validation_results_enqueue_extraction
  AFTER INSERT OR UPDATE ON validation_results
  FOR EACH ROW
  WHEN (NEW.status = 'correct')
  EXECUTE FUNCTION trg_validation_results_enqueue_extraction();
