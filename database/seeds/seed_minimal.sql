-- Seed mínimo da Initial Build (opcional).
INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'demo@trama.local')
ON CONFLICT (email) DO NOTHING;
