-- The stage questions the UI lists for each dataset, chosen from py/4_evaluate.py's
-- "where the arms disagree" output. Each reason quotes the measured result, so re-check
-- the numbers after re-running scripts/evaluate_all.sh (which also runs this file).
-- Only rows for the current database are inserted.

DELETE FROM demo_questions;

INSERT INTO demo_questions (query_id, label, reason, position)
SELECT query_id, label, reason, position
  FROM (VALUES
    ('fiqa', '4641', 'Vector wins',
     'Best answer: vector #2, keyword (ts_rank_cd) #29, BM25 #40, all-words keyword finds nothing.',
     1),
    ('fiqa', '9961', 'Keyword wins',
     'The only answer: BM25 #1, vector #26. RRF dilutes it to #7; the reranker lifts vector''s list to #2.',
     2),
    ('fiqa', '8512', 'Hybrid beats both',
     'The only answer: BM25 #4, vector #9, RRF with BM25 #1 (1/64 + 1/69).',
     3),
    ('fiqa', '988', 'Similar AND contains',
     'Pair with sql/09: must mention "mortgage" returns 1 of 10 rows without iterative scans.',
     4),
    ('nfcorpus', 'PLAIN-307', 'Local hybrid beats the large API model',
     'NDCG@10: small vector 77, BM25 65, tuned blend 97; Embed v4 alone 71.',
     1),
    ('nfcorpus', 'PLAIN-3462', 'Olive oil',
     'Small vector 57, BM25 64, tuned blend 71; Embed v4 alone 60.',
     2),
    ('nfcorpus', 'PLAIN-2240', 'A rare term',
     'Small vector 52, BM25 61, tuned blend 62; Embed v4 alone 65.',
     3),
    ('nfcorpus', 'PLAIN-2510', 'Coffee, for old times',
     'Small vector 61, BM25 71, tuned blend 72; Embed v4 alone 73.',
     4)
  ) AS stage (dataset, query_id, label, reason, position)
 WHERE dataset = current_database();
