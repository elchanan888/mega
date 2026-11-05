#!/bin/bash

# עצירת הסקריפט במקרה של שגיאה
set -e

echo "=================================================="
echo "[*] מתחיל התקנה והגדרה אוטומטית לסביבת MEGA-TOR..."
echo "=================================================="

# 1. עדכון מערכת
echo "[*] מעדכן חבילות מערכת..."
sudo apt update && sudo apt upgrade -y

# 2. התקנת רכיבי תשתית
echo "[*] מתקין Python, Pip, Tor, תלויות רשת וכלי עזר..."
sudo apt install -y python3 python3-pip python3-venv tor curl wget git build-essential

# 3. הגדרת שירות Tor (ControlPort ו-SocksPort)
echo "[*] מגדיר את שירות ה-Tor בקובץ /etc/tor/torrc..."
TORRC="/etc/tor/torrc"

# גיבוי קובץ ההגדרות המקורי אם לא קיים גיבוי
if [ ! -f "${TORRC}.bak" ]; then
    sudo cp "$TORRC" "${TORRC}.bak"
    echo "[+] נוצר גיבוי לקובץ torrc."
fi

# הוספת/וידוא הגדרות ב-torrc
sudo sed -i 's/#SocksPort 9050/SocksPort 127.0.0.1:9050/g' "$TORRC"
sudo sed -i 's/#ControlPort 9051/ControlPort 9051/g' "$TORRC"
sudo sed -i 's/#CookieAuthentication 1/CookieAuthentication 1/g' "$TORRC"

grep -q "SocksPort 127.0.0.1:9050" "$TORRC" || echo "SocksPort 127.0.0.1:9050" | sudo tee -a "$TORRC"
grep -q "ControlPort 9051" "$TORRC" || echo "ControlPort 9051" | sudo tee -a "$TORRC"
grep -q "CookieAuthentication 1" "$TORRC" || echo "CookieAuthentication 1" | sudo tee -a "$TORRC"

# הפעלה מחדש של Tor
sudo systemctl restart tor
sudo systemctl enable tor
echo "[✓] שירות Tor הוגדר והופעל מחדש בהצלחה."

# 4. התאמת הרשאות קבוצת Tor למשתמש הנוכחי
echo "[*] מגדיר הרשאות קריאה ל-Tor Control Cookie עבור המשתמש: $USER..."
sudo usermod -aG debian-tor "$USER"
sudo chmod 755 /run/tor || true
if [ -f /run/tor/control.authcookie ]; then
    sudo chmod 640 /run/tor/control.authcookie
fi
echo "[✓] ההרשאות הוגדרו בהצלחה."

# 5. התקנת MEGA CMD (בדיקה והתקנה אוטומטית)
if ! command -v mega-login &> /dev/null; then
    echo "[*] מתקין MEGA CMD..."
    # זיהוי גרסת אובונטו והורדת החבילה הרשמית
    UBUNTU_VERSION=$(lsb_release -rs)
    echo "[*] זוהתה גרסת Ubuntu: $UBUNTU_VERSION"
    
    # הורדה והתקנה של החבילה הרשמית מבית MEGA
    MEGA_DEB="megacmd-xUbuntu_${UBUNTU_VERSION}_amd64.deb"
    wget -O /tmp/megacmd.deb "https://mega.nz/linux/repo/xUbuntu_${UBUNTU_VERSION}/amd64/megacmd-xUbuntu_${UBUNTU_VERSION}_amd64.deb" || {
        echo "[!] לא נמצאה חבילה ישירה לגרסה זו, מנסה להתקין ממאגר כללי..."
    }
    
    if [ -f /tmp/megacmd.deb ]; then
        sudo apt install -y /tmp/megacmd.deb
        rm -f /tmp/megacmd.deb
    else
        echo "[!] אנא וודא התקנה ידנית של MEGA CMD במידת הצורך."
    fi
else
    echo "[✓] MEGA CMD כבר מותקן במערכת."
fi

# 6. יצירת מבנה תיקיות וקבצי תלויות לפרויקט
PROJECT_DIR="$HOME/שולחן העבודה/mega_automation/server"
echo "[*] יוצר את מבנה התיקיות לפרויקט ב: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"

# יצירת קובץ requirements.txt אוטומטית
echo "[*] יוצר קובץ requirements.txt..."
cat << 'EOF' > "$PROJECT_DIR/requirements.txt"
rich>=13.0.0
pysocks>=1.7.1
requests>=2.31.0
stem>=1.8.2
EOF

# התקנת ספריות פייתון
echo "[*] מתקין את ספריות Python הנדרשות..."
pip3 install --user -r "$PROJECT_DIR/requirements.txt"

echo "=================================================="
echo "[✔] ההתקנה וההגדרות הושלמו בהצלחה מלאה!"
echo "=================================================="
echo "⚠️  חשוב מאוד: כדי שהרשאות ה-Tor ייכנסו לתוקף מיידית,"
echo "הרץ בטרמינל זה את הפקודה הבאה:"
echo "    newgrp debian-tor"
echo "=================================================="
newgrp debian-tor
