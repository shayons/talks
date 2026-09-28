# %% [markdown]
# # 3. Choose the question
#
# Every file in sql/ reads its question from the `active_query` view. This cell sets it.
#
# * A FiQA test question has human judgments, so results can be graded.
# * A question you type is embedded live on Bedrock (`input_type='search_query'`)
#   and is unjudged: no right answers are known for it.
#
# After running a cell, open any `sql/0*.sql` file and run it with SQLTools
# (Cmd+E Cmd+E runs the whole file; select a statement to run just that one).

# %%
from hybrid_lab import questions
from hybrid_lab.db import connect

conn = connect()
for row in conn.execute(
    "SELECT d.position, d.label, q.id, q.body FROM demo_questions d"
    " JOIN queries q ON q.id = d.query_id ORDER BY d.position"
):
    print(row)
conn.rollback()

# %% A judged FiQA test question (change the id to any row printed above)
questions.use(conn, "8")
print(questions.active(conn))

# %% Your own question (unjudged)
questions.ask(conn, "Where should I park my rainy-day fund?")
print(questions.active(conn))
