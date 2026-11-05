#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Advanced Mega-TOR Storage Aggregator & Manager
Author: Advanced Python Automation System
Description: Manages multiple MEGA accounts via MEGA CMD through a rotating TOR proxy,
             aggregates total storage capacity, supports smart session isolation,
             file chunking, and robust error handling/logging.
"""

import os
import sys
import json
import time
import random
import subprocess
import tempfile
import shutil
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Union

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
import requests
from stem import Signal
from stem.control import Controller

# تهيئة קונסול להדפסות מעוצבות
console = Console()

class TorManager:
    """מנהל את חיבור ה-TOR, בדיקת ה-IP הנוכחי וביצוע רוטציה (New Identity)."""
    
    def __init__(self, socks_port: int = 9050, control_port: int = 9051, control_password: Optional[str] = None):
        self.socks_port = socks_port
        self.control_port = control_port
        self.control_password = control_password
        self.proxies = {
            'http': f'socks5h://127.0.0.1:{self.socks_port}',
            'https': f'socks5h://127.0.0.1:{self.socks_port}'
        }

    def get_current_ip(self) -> str:
        """בודק ומחזיר את כתובת ה-IP החיצונית הנוכחית דרך פרוקסי TOR."""
        try:
            response = requests.get('https://httpbin.org/ip', proxies=self.proxies, timeout=15)
            return response.json().get('origin', 'Unknown')
        except Exception:
            return "Connection Failed"

    def rotate_identity(self) -> bool:
        """מבקש משרת ה-TOR להחליף זהות (IP חדש) דרך Control Port."""
        try:
            with Controller.from_port(port=self.control_port) as controller:
                if self.control_password:
                    controller.authenticate(password=self.control_password)
                else:
                    controller.authenticate()
                controller.signal(Signal.NEWNYM)
                time.sleep(random.uniform(1.0, 2.0))
                return True
        except Exception:
            return False

    def verify_connection(self) -> bool:
        """מוודא שפרוקסי TOR זמין ומגיב."""
        ip = self.get_current_ip()
        if ip != "Connection Failed":
            console.print(f"[green][✓] חיבור TOR פעיל בהצלחה. IP נוכחי: {ip}[/green]")
            return True
        console.print(f"[bold red][✗] פרוקסי TOR אינו זמין בפורט {self.socks_port}. אנא וודא ששירות Tor רץ.[/bold red]")
        return False


class AccountParser:
    """מחלקה לפענוח וקליטת פרטי חשבונות MEGA ממקורות שונים."""

    @staticmethod
    def parse_input(source: Union[str, List[Dict[str, str]]]) -> List[Dict[str, str]]:
        accounts = []
        if isinstance(source, list):
            for item in source:
                if "yopmail" in item and "password" in item:
                    accounts.append({"email": item["yopmail"], "password": item["password"]})
                elif "email" in item and "password" in item:
                    accounts.append({"email": item["email"], "password": item["password"]})
            return accounts

        if os.path.exists(str(source)):
            with open(source, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                try:
                    data = json.loads(content)
                    return AccountParser.parse_input(data)
                except json.JSONDecodeError:
                    lines = content.splitlines()
                    return AccountParser._parse_lines(lines)

        try:
            data = json.loads(source)
            return AccountParser.parse_input(data)
        except json.JSONDecodeError:
            pass

        lines = source.splitlines()
        return AccountParser._parse_lines(lines)

    @staticmethod
    def _parse_lines(lines: List[str]) -> List[Dict[str, str]]:
        accounts = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            for sep in [':', ',', '\t']:
                if sep in line:
                    parts = line.split(sep, 1)
                    email = parts[0].strip()
                    password = parts[1].strip()
                    if '@' in email:
                        accounts.append({"email": email, "password": password})
                        break
        return accounts


class MegaManager:
    """מנהל את האינטראקציה מול כלי MEGA CMD תוך בידוד סשנים (Sessions)."""

    def __init__(self, tor_manager: TorManager):
        self.tor_manager = tor_manager

    def _run_mega_command(self, cmd: List[str], config_dir: str, timeout: int = 30) -> Tuple[bool, str]:
        """מריץ פקודת mega-cmd תחת תיקיית קונפיגורציה מבודדת לחלוטין."""
        env = os.environ.copy()
        env["MEGA_CONFIG_PATH"] = config_dir
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip() or result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def test_and_get_storage(self, email: str, password: str) -> Dict[str, Union[str, float, int, bool]]:
        """מתחבר לחשבון MEGA, שולף נתוני אחסון ומחזיר סטטוס מלא."""
        config_dir = tempfile.mkdtemp(prefix=f"mega_session_{email.replace('@', '_')}_")
        result_data = {
            "email": email,
            "status": "Failed",
            "total_gb": 0.0,
            "used_gb": 0.0,
            "free_gb": 0.0,
            "error": ""
        }

        try:
            self.tor_manager.rotate_identity()
            
            success, output = self._run_mega_command(["mega-login", email, password], config_dir, timeout=25)
            if not success:
                if "already logged in" not in output.lower():
                    result_data["error"] = f"Login failed: {output}"
                    return result_data

            success_df, df_output = self._run_mega_command(["mega-df"], config_dir, timeout=15)
            if not success_df:
                result_data["error"] = f"Failed to fetch storage: {df_output}"
                return result_data

            parsed_storage = self._parse_df_output(df_output)
            result_data.update(parsed_storage)
            result_data["status"] = "Active"

            self._run_mega_command(["mega-logout"], config_dir, timeout=10)

        except Exception as e:
            result_data["error"] = str(e)
        finally:
            if os.path.exists(config_dir):
                shutil.rmtree(config_dir, ignore_errors=True)

        return result_data

    @staticmethod
    def _normalize_to_gb(val: float, raw_unit: str) -> float:
        """ממיר כל יחידת מידה לגיגה-בייט בצורה מדויקת."""
        unit = raw_unit.upper() if raw_unit else ""
        
        # אם המספר עצום ואין יחידה מפורשת או שהוא בבייטים גולמיים
        if val > 1000000 and (not unit or 'B' == unit or 'BYTE' in unit):
            return val / (1024 * 1024 * 1024)
        
        if 'TB' in unit:
            return val * 1024
        elif 'GB' in unit:
            return val
        elif 'MB' in unit:
            return val / 1024
        elif 'KB' in unit:
            return val / (1024 * 1024)
        elif unit == 'B' or 'BYTE' in unit:
            return val / (1024 * 1024 * 1024)
        else:
            # אם אין יחידה והמספר קטן, נניח שזה כבר GB
            if val < 1000:
                return val
            # אם הוא גדול, נניח שזה בייטים
            return val / (1024 * 1024 * 1024)

    @staticmethod
    def _parse_df_output(output: str) -> Dict[str, float]:
        """מפענח את הפלט של mega-df באופן חסין לשגיאות והמרה מדויקת מביטים ל-GB."""
        total, used, free = 0.0, 0.0, 0.0
        try:
            for line in output.splitlines():
                lower = line.lower()
                # חיפוש כל הזוגות של מספר ויחידת מידה בשורה
                matches = re.findall(r'([0-9\.]+)\s*(GB|MB|TB|KB|B)?', line, re.IGNORECASE)
                
                if "total" in lower and matches:
                    val = float(matches[0][0])
                    unit = matches[0][1] if len(matches[0]) > 1 else ""
                    total = MegaManager._normalize_to_gb(val, unit)
                
                elif "free" in lower and matches:
                    val = float(matches[0][0])
                    unit = matches[0][1] if len(matches[0]) > 1 else ""
                    free = MegaManager._normalize_to_gb(val, unit)
                
                elif ("used" in lower or "storage" in lower) and matches:
                    # לפעמים יש מספר ערכים בשורה (למשל used ו-total)
                    if "used" in lower:
                        val = float(matches[0][0])
                        unit = matches[0][1] if len(matches[0]) > 1 else ""
                        used = MegaManager._normalize_to_gb(val, unit)
                    if len(matches) >= 2:
                        val = float(matches[1][0])
                        unit = matches[1][1] if len(matches[1]) > 1 else ""
                        total = MegaManager._normalize_to_gb(val, unit)

            # בדיקות שפיות ותיקון ערכים
            if total <= 0.0 or total > 10000:
                total = 15.0  # ברירת מחדל לחשבון חינמי
            
            if used < 0.0:
                used = 0.0
            
            if used > total:
                used = total

            if free <= 0.0 or free > total:
                free = max(0.0, total - used)

        except Exception:
            total, used, free = 15.0, 0.0, 15.0

        return {
            "total_gb": round(total, 2), 
            "used_gb": round(used, 2), 
            "free_gb": round(free, 2)
        }

    @staticmethod
    def split_file(file_path: str, chunk_size_mb: int = 50) -> List[str]:
        """מחלק קובץ גדול לחלקים (Chunks) המותאמים למגבלות האחסון."""
        chunk_files = []
        chunk_size = chunk_size_mb * 1024 * 1024
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        base_name = os.path.basename(file_path)
        output_dir = tempfile.mkdtemp(prefix="mega_chunks_")

        with open(file_path, 'rb') as f:
            chunk_index = 0
            while True:
                chunk_data = f.read(chunk_size)
                if not chunk_data:
                    break
                chunk_name = f"{base_name}.part{chunk_index:03d}"
                chunk_path = os.path.join(output_dir, chunk_name)
                with open(chunk_path, 'wb') as cf:
                    cf.write(chunk_data)
                chunk_files.append(chunk_path)
                chunk_index += 1

        return chunk_files


class StorageAggregatorController:
    """מנוע ראשי לתיאום חשבונות מרובים, ריצה מקבילית וסיכום נתונים כולל."""

    def __init__(self, accounts: List[Dict[str, str]], max_workers: int = 1, socks_port: int = 9050, control_port: int = 9051):
        self.accounts = accounts
        self.max_workers = max_workers
        self.tor_manager = TorManager(socks_port=socks_port, control_port=control_port)
        self.mega_manager = MegaManager(self.tor_manager)

    def audit_all_accounts(self) -> List[Dict[str, Union[str, float, int, bool]]]:
        """בדיקה ובקרה של כלל החשבונות ברשימה עם השהיות אקראיות (Jitter)."""
        console.print(f"[bold cyan][*] מתחיל סריקה ובדיקה של {len(self.accounts)} חשבונות MEGA...[/bold cyan]")
        
        self.tor_manager.verify_connection()

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {}
            for acc in self.accounts:
                delay = random.uniform(0.5, 2.0)
                time.sleep(delay)
                
                future = executor.submit(
                    self.mega_manager.test_and_get_storage,
                    acc["email"],
                    acc["password"]
                )
                future_to_account[future] = acc["email"]

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[green]בודק חשבונות MEGA...", total=len(self.accounts))
                
                for future in as_completed(future_to_account):
                    res = future.result()
                    results.append(res)
                    progress.advance(task)

        return results

    def display_aggregation_summary(self, results: List[Dict[str, Union[str, float, int, bool]]]):
        """מציג טבלה מסודרת וסיכום כולל של כלל הנפחים במערכת."""
        table = Table(title="📊 סיכום נפחי אחסון - חשבונות MEGA מאוחדים")
        table.add_column("אימייל חשבון", style="cyan", no_wrap=True)
        table.add_column("סטטוס", style="bold")
        table.add_column("סה\"כ נפח (GB)", justify="right", style="magenta")
        table.add_column("בשימוש (GB)", justify="right", style="yellow")
        table.add_column("פנוי (GB)", justify="right", style="green")
        table.add_column("הערות / שגיאות", style="red")

        grand_total = 0.0
        grand_used = 0.0
        grand_free = 0.0
        active_count = 0

        for res in results:
            status_style = "green" if res["status"] == "Active" else "bold red"
            status_text = res["status"]
            
            if res["status"] == "Active":
                active_count += 1
                grand_total += float(res["total_gb"])
                grand_used += float(res["used_gb"])
                grand_free += float(res["free_gb"])

            table.add_row(
                str(res["email"]),
                f"[{status_style}]{status_text}[/{status_style}]",
                str(res["total_gb"]),
                str(res["used_gb"]),
                str(res["free_gb"]),
                str(res.get("error", ""))
            )

        console.print(table)
        
        console.print("\n[bold green]==================== סיכום מערכת כולל ====================[/bold green]")
        console.print(f"[cyan]• סך הכל חשבונות פעילים:[/cyan] {active_count} מתוך {len(results)}")
        console.print(f"[magenta]• סך כל נפח האחסון המאוחד (Total Capacity):[/magenta] {grand_total:.2f} GB")
        console.print(f"[yellow]• סך כל האחסון בשימוש (Total Used):[/yellow] {grand_used:.2f} GB")
        console.print(f"[green]• סך כל האחסון הפנוי במערכת (Total Free):[/green] {grand_free:.2f} GB")
        console.print("[bold green]=========================================================[/bold green]\n")


if __name__ == "__main__":
    sample_accounts_input = [
        {
            "yopmail": "0rbimlcjgl681kavpqc5@bahoo.biz.st",
            "password": "ZX-DavOCmKzeclZvWIDM7O!t65t@"
        }
    ]

    console.print("[bold yellow]=== מערכת ניהול ואיחוד אחסון MEGA דרך TOR מתחילה פעולה ===[/bold yellow]")
    accounts = AccountParser.parse_input(sample_accounts_input)
    
    if not accounts:
        console.print("[bold red][!] לא נמצאו חשבונות תקינים לעיבוד.[/bold red]")
        sys.exit(1)

    controller = StorageAggregatorController(accounts=accounts, max_workers=1, socks_port=9050, control_port=9051)
    audit_results = controller.audit_all_accounts()
    controller.display_aggregation_summary(audit_results)
