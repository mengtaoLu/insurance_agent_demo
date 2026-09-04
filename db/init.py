import sqlite3

def init_db():

    conn = sqlite3.connect('data.db')
    cur = conn.cursor()

    with open('db/sqls/init.sql','r',encoding='utf-8') as f:
        sql_content = f.read()

        sqls = sql_content.split(';')

    for sql in sqls:
        print(sql)
        cur.execute(sql)
        conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    init_db()