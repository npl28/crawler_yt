import psycopg2
from psycopg2.extras import RealDictCursor
import traceback

# === Thông tin kết nối DB ===
DB_CONFIG = {
    # "host": "localhost",
    # "port": "5432",
    # "dbname": "mydb",
    # "user": "postgres",
    # "password": "loi"
    "host": "14.224.225.89",
    "port": "5432",
    "dbname": "aimdb",
    "user": "crawler01",
    "password": "yourpassword01"

}

# === Hàm kết nối ===
def get_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print("❌ Không thể kết nối PostgreSQL:", e)
        return None

# === SELECT query ===
def select_query(query, params=None):
    conn = get_connection()
    if conn is None:
        return []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()
            return results
    except Exception as e:
        print("❌ Lỗi SELECT:", e)
        return []
    finally:
        conn.close()

# === INSERT query ===
def insert_query(query, params):
    conn = get_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return True
    except Exception as e:
        print("❌ Lỗi INSERT {query}:", e )
        conn.rollback()
        return False
    finally:
        conn.close()

# === UPDATE query ===
def update_query(query, params):
    conn = get_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return True
    except Exception as e:
        print("❌ Lỗi UPDATE:", e)
        conn.rollback()
        return False
    finally:
        conn.close()

# === DELETE query ===
def delete_query(query, params):
    conn = get_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
            return True
    except Exception as e:
        print("❌ Lỗi DELETE:", e)
        conn.rollback()
        return False
    finally:
        conn.close()

def validate_individual(individual_name, individual_link):
    # print("validate_individual")
    if "ẩn danh" in individual_name.lower():
        return False
    
    individual_data = select_query("SELECT 1 FROM fb_individual WHERE url = %s LIMIT 1", (individual_link,))
    if not individual_data:
        # print(f"❌ validate không tìm thấy cá nhân với ID: _{individual_link}")
        return True
    else:
        # print(f"✅ Cá nhân đã tồn tại: {individual_data[0]['individual_name']}")
        return False
    

def validate_post_fb(individual_id, content):
    # print("validate_post_fb")
    if len(content) < 50:
        post_data = select_query(
            "SELECT * FROM fb_post WHERE individual_id = %s AND content = %s",
            (individual_id, content)
        )
    else:
        post_data = select_query(
            "SELECT * FROM fb_post WHERE individual_id = %s AND LEFT(content, 50) = LEFT(%s, 50)",
            (individual_id, content)
        )
    if not post_data:
        return True
    else:
        return False

def validate_reply(post_id, individual_id, reply_content):
    # print("validate_reply")
    if len(reply_content) < 10:
        reply_data = select_query(
            "SELECT * FROM fb_reply WHERE post_id = %s AND individual_id = %s AND rely_content = %s",
            (post_id, individual_id, reply_content)
        )
    else:
        reply_data = select_query(
            "SELECT * FROM fb_reply WHERE post_id = %s AND individual_id = %s AND LEFT(rely_content, 10) = LEFT(%s, 10)",
            (post_id, individual_id, reply_content)
        )
    return len(reply_data) == 0
    
def insert_individual(individual_id, individual_name, url, is_post):
    try:
        s_id = None  # Khởi tạo rõ ràng
        if validate_individual(individual_name, url):
            print(f"✅ Thêm cá nhân mới: {individual_id}__{url}")
            _ = insert_query(
                "INSERT INTO fb_individual (individual_id, individual_name, url, num_post) VALUES (%s, %s, %s, %s)",
                (individual_id, "user", url, 1 if is_post else 0)
            )
            s_id = individual_id
        else:
            s_id = get_individual_id(individual_name, url)
            print(f"✅ Cá nhân đã tồn tại: {s_id}")
            if is_post:
                _ = update_query(
                    "UPDATE fb_individual SET num_post = num_post + 1 WHERE individual_id = %s",
                    (s_id,)
                )
    except Exception as e:
        print(f"❌ Lỗi khi insert_individual {individual_id}_{url}: {e}")
        traceback.print_exc()

    return s_id

# def insert_individual(individual_id, individual_name, url, is_post):
#     try:
#         # Luôn lưu tên ẩn danh
#         anon_name = "user"
#         post_increment = 1 if is_post else 0

#         query = """
#             INSERT INTO fb_individual (individual_id, individual_name, url, num_post)
#             VALUES (%s, %s, %s, %s)
#             ON DUPLICATE KEY UPDATE
#                 num_post = num_post + VALUES(num_post)
#         """
#         params = (individual_id, anon_name, url, post_increment)

#         _ = insert_query(query, params)

#         return individual_id

#     except Exception as e:
#         print(f"❌ Lỗi khi insert_individual {individual_id}_{url}: {e}")
#         traceback.print_exc()
#         return None


def insert_post_fb(post_id, timestamp, individual_id, content, source, num_like, num_reply, is_image, is_video, image_url, video_url, estimate_reach):
    ok = False
    if validate_post_fb(individual_id, content):
        ok = insert_query(
            "INSERT INTO fb_post (post_id, timestamp, individual_id, content, source, num_like, num_reply, is_image, is_video, image_url, video_url, estimate_reach) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                (post_id, timestamp, individual_id, content, source, num_like, num_reply, is_image, is_video, image_url, video_url, estimate_reach)
        )
    return ok

def insert_reply(reply_id, post_id, individual_id, reply_content, num_like, is_image, is_video, image_url, video_url, related_reply_id):
    ok = False
    if validate_reply(post_id, individual_id, reply_content): 
        ok = insert_query(
            "INSERT INTO fb_reply (reply_id, post_id, individual_id, rely_content, num_like, is_image, is_video, image_url, video_url, related_reply_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (reply_id, post_id, individual_id, reply_content, num_like, is_image, is_video, image_url, video_url, related_reply_id)
        )
    return ok    

def get_individual_id(individual_name, individual_link):
    s_id_result = None
    _id = ""
    if "ẩn danh" in individual_name.lower():
        s_id_result = select_query(
            "SELECT individual_id FROM fb_individual WHERE individual_name like '%ẩn danh%'"
    )
    else:
        s_id_result = select_query(
            "SELECT individual_id FROM fb_individual WHERE url = %s",
            (individual_link,)
        )
    if s_id_result and len(s_id_result) > 0:
        _id = s_id_result[0]['individual_id']

    return _id

def validate_yt_post(post_name, post_url):
    post_data = select_query(
        "SELECT 1 FROM yt_post WHERE post_name = %s AND post_url = %s LIMIT 1",
        (post_name, post_url)
    )
    return not post_data

def insert_yt_post(post_id, post_name, post_url, post_content, post_at):
    # if validate_yt_post(post_name, post_url):
    ok = insert_query(
        "INSERT INTO yt_post (post_id, post_name, post_url, post_content, post_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (post_id, post_name, post_url, post_content, post_at)
    )
    return ok

def update_yt_post_content(post_id, post_content):
    return update_query(
        "UPDATE yt_post SET post_content = %s, post_processed = TRUE WHERE post_id = %s",
        (post_content, post_id)
    )

