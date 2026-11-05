from mega_tor_manager import AccountParser, StorageAggregatorController
from rich.console import Console

console = Console()

if __name__ == "__main__":
    console.print("[bold yellow]=== טעינת חשבונות MEGA והרצת בדיקה ===[/bold yellow]")
    
    accounts_file = "../users/accounts.json"
    
    try:
        accounts = AccountParser.parse_input(accounts_file)
    except Exception as e:
        console.print(f"[bold red][!] שגיאה בטעינת קובץ החשבונות: {e}[/bold red]")
        accounts = []

    console.print(f"[cyan]נמצאו {len(accounts)} חשבונות תקינים לעיבוד.[/cyan]")

    if not accounts:
        console.print("[bold red][!] רשימת החשבונות ריקה. בדוק את נתיב הקובץ.[/bold red]")
        exit(1)

    # שימוש ב-max_workers=1 מונע התנגשויות מול mega-cmd וחסימות Rate Limit
    controller = StorageAggregatorController(
        accounts=accounts, 
        max_workers=1, 
        socks_port=9050, 
        control_port=9051
    )
    
    audit_results = controller.audit_all_accounts()
    controller.display_aggregation_summary(audit_results)
