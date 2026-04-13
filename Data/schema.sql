-- Drop tables 
DROP TABLE IF EXISTS troubleshooting_kb;

-- Create Extensions
CREATE EXTENSION IF NOT EXISTS google_ml_integration;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create build_environments table
CREATE TABLE troubleshooting_kb (
    error_id SERIAL PRIMARY KEY,
    stack_trace TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    solution TEXT NOT NULL,
    stack_trace_embedding vector(768)
);