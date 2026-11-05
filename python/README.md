# Advanced Mega-TOR Storage Aggregator & Manager

סקריפט Python ארגוני ומתקדם לניהול, בדיקה ואיחוד נפחי אחסון ממספר רב של חשבונות **MEGA** במקביל. הסקריפט משלב אבטחת מידע מתקדמת דרך ניתוב פרוקסי **TOR** עם רוטציות IP אוטומטיות, בידוד מוחלט של קבצי מטמון וסשנים (Session Isolation), תמיכה בריבוי תהליכים (Multi-threading), והשהיות אקראיות חכמות (Jitter) למניעת חסימות Rate Limit.

---

## 🏗️ ארכיטקטורת המערכת והמודולים

הפרויקט מחולק למודולים עצמאיים המבטיחים תחזוקה קלה, מודולריות ואמינות גבוהה:

1. **`TorManager` (ניהול פרוקסי TOR):**
   - אחראי על חיבור דרך פרוקסי SOCKS5 (`127.0.0.1:9050`).
   - בודק תקינות IP חיצוני.
   - מבצע רוטציית IP דינמית דרך ה-Control Port של Tor (`9051`) באמצעות פקודת `NEWNYM`.

2. **`AccountParser` (קליטה ופענוח נתונים):**
   - יודע לקלוט רשימות חשבונות גמישות: מחרוזות JSON, קבצי טקסט חיצוניים או רשימות מילונים.
   - תומך בפורמט שורות פשוט `email:password` (מופרד בפסיקים, נקודתיים או טאבים).

3. **`MegaManager` (ממשק מול MEGA CMD):**
   - עוטף את כלי השרת של MEGA (`mega-login`, `mega-df`, `mega-logout`).
   - **בידוד סשנים (Session Isolation):** יוצר תיקיית קונפיגורציה זמנית נפרדת לחלוטין (`MEGA_CONFIG_PATH`) לכל חשבון כדי למנוע התנגשויות Cache או דליפת פרטי הזדהות.
   - **חלוקת קבצים (File Chunking):** מנגנון מובנה לחלוקת קבצים גדולים למקטעים (`Chunks`) המותאמים למגבלת האחסון של חשבונות בודדים.

4. **`StorageAggregatorController` (בקר ראשי ואיחוד נתונים):**
   - מנהל את הריצה המקבילית באמצעות `ThreadPoolExecutor`.
   - אוסף את נתוני האחסון מכלל החשבונות ומפיק דוח טבלאי מעוצב וסיכום מערכת כולל.

---

## ⚙️ דרישות מערכת והתקנה

### 1. התקנת רכיבי מערכת (Linux / Ubuntu / Debian)
```bash
# עדכון מערכת
sudo apt update && sudo apt upgrade -y

# התקנת שירות Tor
sudo apt install tor -y
sudo systemctl enable tor
sudo systemctl start tor

# מתן הרשאות קריאה ל-Tor Control Cookie למשתמש שלך
sudo usermod -aG debian-tor $USER
sudo chmod 755 /run/tor
sudo chmod 640 /run/tor/control.authcookie
newgrp debian-tor




