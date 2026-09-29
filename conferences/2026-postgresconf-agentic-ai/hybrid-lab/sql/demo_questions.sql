-- Curated teaching examples, selected after evaluation to show contrasting outcomes.
-- They are not a representative sample. Use results/summary.md for aggregate claims.
-- Only rows for the current dataset database are inserted.

DELETE FROM demo_questions;

INSERT INTO demo_questions (query_id, label, reason, position)
SELECT query_id, label, reason, position
  FROM (VALUES
    ('fiqa', '4827', 'Vector wins',
     'The answer explains commissions, hourly fees and portfolio-based fees. Embed v4 ranks it #1; BM25 leaves it outside its top 50. RRF gives it credit from only the vector list, so documents found by both lists push it down to #17.', 1),
    ('fiqa', '9961', 'Keyword wins',
     'The answer explicitly discusses both 403b and 401k plans. BM25 puts it #1, while Embed v4 ranks it #26. Equal-weight RRF moves it to #7, still below the keyword result; reranking the vector candidates recovers it at #2.', 2),
    ('fiqa', '8512', 'Hybrid beats both',
     'Both methods find the answer about cash contributions and in-kind IRA transfers, but neither ranks it first: BM25 #4, vector #9. RRF adds credit from both lists, lifting their shared answer to #1. Agreement beats either list alone here.', 3),
    ('fiqa', '9598', 'Reranker rescues',
     'The answer explains that an index fund follows its index rather than picking stocks. Vector search finds it at #11, just outside the displayed top 10. The reranker reads the question and candidate text together and promotes it to #1.', 4),
    ('scifact', '185', 'Hybrid finds agreement',
     'Both lists find the same study of genetic and environmental factors: BM25 at #4, local vector at #3. Their normalized scores combine to lift that evidence to #2. The gain comes from better placement of the same paper, not an extra answer.', 1),
    ('scifact', '237', 'An exact gene name',
     'The judged abstract shares the specific terms “sporulation” and “Bacillus subtilis” with the claim. BM25 ranks it #1 and both vector models rank it #2. The blend keeps it at #1: a tie with BM25, and a gain over vector alone.', 2),
    ('scifact', '1363', 'Keywords find the evidence',
     'The judged abstract explicitly mentions both arterioles and venules. BM25 ranks it #1; neither vector model includes it in its top 50. The blend can recover it through the keyword list, but dilutes that signal and places it only at #5.', 3),
    ('scifact', '535', 'Blending can hurt',
     'Both vector models put the judged blood-pressure study at #1. It is absent from the BM25 candidate list, so the blend gets no keyword contribution for it. Other candidates gain ground and push the answer to #5. Adding a weaker list hurts here.', 4),
    ('nfcorpus', 'PLAIN-307', 'Local hybrid beats the frontier model',
     'The lists complement each other: BM25 ranks one known answer #2 that local vector leaves at #19. Blending brings it to #4 and puts the guideline paper at #1. All three known answers reach the top four, producing 97 versus 77 for local vector.', 1),
    ('nfcorpus', 'PLAIN-3462', 'Olive oil',
     'Each local input has six known answers in its top 10, with different coverage. The blend brings seven into view and keeps the Mediterranean-diet paper at #1. Embed v4 also finds seven, but their placement and graded relevance yield 60 versus the blend’s 71.', 2),
    ('nfcorpus', 'PLAIN-418', 'Fresh or frozen fruit',
     'BM25 finds the raspberry-freezing study at #1; local vector leaves it at #11. The blend brings it to #3 while keeping the strawberry comparison at #1. Two known answers now rank highly, matching BM25’s score and improving on local vector.', 3),
    ('nfcorpus', 'PLAIN-1752', 'Only the frontier finds it',
     'The judged paper concerns bile-acid binding in cooked vegetables and never says “okra,” so BM25 cannot match the query term. Embed v4 retrieves it at #1. Neither local vector nor its blend puts it in the top 10: semantic retrieval succeeds beyond literal wording.', 4),
    ('scidocs', '1258db72eec4bbf02e29edf5bb0c300491a01242', 'Hybrid recovers citations',
     'The lists recover different cited papers. A shared sentence-classification paper moves from #2 in each list to blend #1, while a BM25 #1 citation rises from local vector #18 to blend #3. The blend retains four of five known citations in the top 10.', 1),
    ('scidocs', '39d428fd8c6b73ed070921a856f03c2c5b5377ba', 'Speech synthesis',
     'Both lists find the same two cited papers on neural speech methods, but at different ranks: #2/#6 and #6/#5. Combining their scores lifts those citations to #1 and #2. Agreement improves their placement even with the fixed 50/50 blend.', 2),
    ('scidocs', 'a7633785229e2db5ef7d4dd8b7e63b017c5eb3d3', 'Vector wins: nTorrent',
     'The task is to recover cited papers, not just titles with matching words. Embed v4 places four known citations at #1, #3, #4 and #5, including the foundational Named Data Networking paper. The other three displayed methods find none in their top 10.', 3),
    ('scidocs', '21b1180af3087c1333708a9873f6d473eabe6751', 'Blending can hurt',
     'Local vector finds three known citations; BM25 finds none in its top 10. Adding keyword scores with a fixed 50/50 weight pushes two of those citations out of view, leaving just one. The weaker keyword ranking overwhelms useful vector results here.', 4)
  ) AS stage (dataset, query_id, label, reason, position)
 WHERE dataset = current_database();
