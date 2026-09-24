CREATE TABLE IF NOT EXISTS hotels (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL,
  display_name TEXT,
  legal_name TEXT,
  siret TEXT,
  vat_number TEXT,
  address TEXT,
  zip_code TEXT,
  city TEXT,
  country TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_archives (
  id INTEGER PRIMARY KEY,
  hotel_id INTEGER NOT NULL REFERENCES hotels(id),
  archive_name TEXT NOT NULL,
  root_filename TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('annee','monthly','mois','range','daily')),
  period_start TEXT,
  period_end TEXT,
  precedence INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  rsa_signature TEXT,
  byte_size INTEGER,
  html_bytes INTEGER,
  document_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  section_counts_json TEXT,
  status TEXT NOT NULL,
  error TEXT,
  ingested_at TEXT NOT NULL,
  UNIQUE (hotel_id, archive_name),
  UNIQUE (hotel_id, sha256)
);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY,
  hotel_id INTEGER NOT NULL REFERENCES hotels(id),
  source_archive_id INTEGER REFERENCES source_archives(id),
  source_precedence INTEGER NOT NULL,
  nf525_ticket_id TEXT,
  document_type TEXT NOT NULL,
  document_number TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  business_date TEXT NOT NULL,
  amount_ht_cents INTEGER,
  amount_tva_cents INTEGER,
  amount_ttc_cents INTEGER,
  currency TEXT NOT NULL DEFAULT 'EUR',
  payment_methods TEXT NOT NULL DEFAULT '',
  customer_name TEXT NOT NULL DEFAULT '',
  customer_vat TEXT NOT NULL DEFAULT '',
  seller_name TEXT NOT NULL DEFAULT '',
  operator_name TEXT NOT NULL DEFAULT '',
  terminal_code TEXT NOT NULL DEFAULT '',
  operation_type TEXT NOT NULL DEFAULT '',
  ticket_status TEXT NOT NULL DEFAULT '',
  print_number INTEGER,
  number_of_lines INTEGER,
  signature TEXT NOT NULL DEFAULT '',
  html_fragment TEXT NOT NULL,
  html_sha256 TEXT NOT NULL,
  search_text TEXT NOT NULL DEFAULT '',
  vat_lines_json TEXT NOT NULL DEFAULT '[]',
  parse_warnings TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (hotel_id, document_type, document_number)
);

CREATE TABLE IF NOT EXISTS invoice_payments (
  id INTEGER PRIMARY KEY,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  paid_at TEXT,
  payment_method TEXT NOT NULL DEFAULT '',
  payment_type TEXT NOT NULL DEFAULT '',
  payment_mode TEXT NOT NULL DEFAULT '',
  account_number TEXT NOT NULL DEFAULT '',
  amount_cents INTEGER,
  currency TEXT NOT NULL DEFAULT 'EUR'
);

CREATE TABLE IF NOT EXISTS ingestion_logs (
  id INTEGER PRIMARY KEY,
  hotel_id INTEGER REFERENCES hotels(id),
  source_archive_id INTEGER REFERENCES source_archives(id),
  level TEXT NOT NULL CHECK (level IN ('info','warning','error')),
  event TEXT NOT NULL,
  message TEXT NOT NULL,
  document_number TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoices_hotel_date
  ON invoices (hotel_id, business_date, id);
CREATE INDEX IF NOT EXISTS idx_invoices_hotel_ttc
  ON invoices (hotel_id, amount_ttc_cents);
CREATE INDEX IF NOT EXISTS idx_invoices_number
  ON invoices (document_number);
CREATE INDEX IF NOT EXISTS idx_invoices_customer
  ON invoices (customer_name);
CREATE INDEX IF NOT EXISTS idx_payments_invoice
  ON invoice_payments (invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_mode
  ON invoice_payments (payment_mode);
CREATE INDEX IF NOT EXISTS idx_logs_archive
  ON ingestion_logs (source_archive_id, id);

CREATE VIRTUAL TABLE IF NOT EXISTS invoices_fts USING fts5(
  document_number,
  customer_name,
  seller_name,
  operator_name,
  payment_methods,
  search_text,
  tokenize = 'unicode61 remove_diacritics 2',
  content = 'invoices',
  content_rowid = 'id'
);

CREATE TRIGGER IF NOT EXISTS invoices_fts_insert AFTER INSERT ON invoices BEGIN
  INSERT INTO invoices_fts(
    rowid, document_number, customer_name, seller_name,
    operator_name, payment_methods, search_text
  ) VALUES (
    new.id, new.document_number, new.customer_name, new.seller_name,
    new.operator_name, new.payment_methods, new.search_text
  );
END;

CREATE TRIGGER IF NOT EXISTS invoices_fts_delete AFTER DELETE ON invoices BEGIN
  INSERT INTO invoices_fts(
    invoices_fts, rowid, document_number, customer_name, seller_name,
    operator_name, payment_methods, search_text
  ) VALUES (
    'delete', old.id, old.document_number, old.customer_name, old.seller_name,
    old.operator_name, old.payment_methods, old.search_text
  );
END;

CREATE TRIGGER IF NOT EXISTS invoices_fts_update AFTER UPDATE ON invoices BEGIN
  INSERT INTO invoices_fts(
    invoices_fts, rowid, document_number, customer_name, seller_name,
    operator_name, payment_methods, search_text
  ) VALUES (
    'delete', old.id, old.document_number, old.customer_name, old.seller_name,
    old.operator_name, old.payment_methods, old.search_text
  );
  INSERT INTO invoices_fts(
    rowid, document_number, customer_name, seller_name,
    operator_name, payment_methods, search_text
  ) VALUES (
    new.id, new.document_number, new.customer_name, new.seller_name,
    new.operator_name, new.payment_methods, new.search_text
  );
END;
