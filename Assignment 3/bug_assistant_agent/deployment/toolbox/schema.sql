-- Production schema for the bug assistant (Cloud SQL / AlloyDB for PostgreSQL).
-- Seed rows: see mcp_server/seed_tickets.json (insert title, description, assignee, priority, status).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS google_ml_integration;  -- enables embedding() in Cloud SQL / AlloyDB

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id     SERIAL PRIMARY KEY,
    title         VARCHAR(255) NOT NULL,
    description   TEXT NOT NULL,
    assignee      VARCHAR(100) DEFAULT '',
    priority      VARCHAR(20)  NOT NULL DEFAULT 'P3 - Low',
    status        VARCHAR(20)  NOT NULL DEFAULT 'Open',
    creation_time TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_time  TIMESTAMP    NOT NULL DEFAULT NOW(),
    embedding     vector(768)
);

-- Keep the embedding and updated_time in sync on every write.
CREATE OR REPLACE FUNCTION tickets_before_write() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'INSERT' OR NEW.title IS DISTINCT FROM OLD.title
     OR NEW.description IS DISTINCT FROM OLD.description THEN
    NEW.embedding := embedding('text-embedding-005', NEW.title || ' ' || NEW.description)::vector;
  END IF;
  NEW.updated_time := NOW();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS tickets_bw ON tickets;
CREATE TRIGGER tickets_bw BEFORE INSERT OR UPDATE ON tickets
  FOR EACH ROW EXECUTE FUNCTION tickets_before_write();
