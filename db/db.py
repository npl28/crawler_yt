# db.py
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="mydb",
            user="postgres",
            password="loi",
            port=5432  # Cổng mặc định PostgreSQL
        )
        return conn
    except Exception as e:
        print("❌ Lỗi khi kết nối đến PostgreSQL:", e)
        return None
    
# select * from fb_individual
# delete from fb_individual

# select * from fb_post
# delete from fb_post

# select * from fb_reply
# delete from fb_reply
# drop table fb_individual
# CREATE TABLE fb_individual (
#     no serial,              -- ID người dùng (user ID, page ID, group ID...)
#     individual_id varchar(50) NOT NULL PRIMARY KEY,                 -- ID người trả lời (user)
# 	individual_name varchar(200) NOT NULL,                 -- ID người trả lời (user)
#     url TEXT,                         -- URL profile hoặc fanpage
#     num_post INTEGER DEFAULT 0,       -- Số lượng bài viết đã đăng
#     expected_reach INTEGER            -- Ước lượng số người tiếp cận trung bình
# );

# # drop table fb_reply
# CREATE TABLE fb_reply (
#     no SERIAL ,                       -- ID tự tăng
# 	reply_id varchar(50) NOT NULL PRIMARY KEY,
#     post_id varchar(50) NOT NULL,  -- Liên kết bài viết
#     individual_id varchar(50) NOT NULL,                 -- ID người trả lời (user)
#     rely_content TEXT,                                -- Nội dung comment/trả lời
#     num_like INTEGER DEFAULT 0,                  -- Số lượt like
#     is_image BOOLEAN DEFAULT FALSE,              -- Có ảnh không
#     is_video BOOLEAN DEFAULT FALSE,              -- Có video không
#     image_url TEXT,                              -- URL ảnh (nếu có)
#     video_url TEXT,                               -- URL video (nếu có)
#     related_reply_id varchar(50) NULL
# );

#  drop table fb_post
# CREATE TABLE fb_post (
#     no SERIAL ,                       -- ID tự tăng
# 	  post_id varchar(50) not null PRIMARY KEY,
#     timestamp bigint NOT NULL,                -- Thời gian đăng bài
#     individual_id TEXT NOT NULL,                 -- ID người đăng (user/page)
#     content TEXT,                                -- Nội dung bài viết
#     source TEXT,                                 -- Nguồn bài viết (VD: group/page/profile)
#     num_like INTEGER DEFAULT 0,                  -- Số lượt like
#     num_reply INTEGER DEFAULT 0,                 -- Số lượt bình luận
#     is_image BOOLEAN DEFAULT FALSE,              -- Có ảnh không
#     is_video BOOLEAN DEFAULT FALSE,              -- Có video không
#     image_url TEXT,                              -- URL ảnh (nếu có)
#     video_url TEXT,                              -- URL video (nếu có)
#     estimate_reach INTEGER                       -- Ước lượng số người tiếp cận
# );

# AIM database server info :
# 14.224.225.89
# default port của postgres: 5432
# username : crawler01
# password: yourpassword01
# db name : aimdb


# CREATE TABLE IF NOT EXISTS public.yt_group
# (
#     yt_id character varying(20) COLLATE pg_catalog."default" NOT NULL PRIMARY KEY,
#     yt_name text,
#     yt_link_full text,
# 	yt_link text
# )

# CREATE TABLE IF NOT EXISTS yt_post
# (
#     post_id character varying(20) COLLATE pg_catalog."default" NOT NULL PRIMARY KEY,
#     post_name text,
#     post_url text,
# 	post_content text
# )