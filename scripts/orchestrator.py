import subprocess
import sys

def run_step(script, args=[]):
    print(f"--- Running {script} ---")
    cmd = ["python3", f"scripts/{script}"] + args
    subprocess.run(cmd)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 orchestrator.py <query>")
        return

    query = sys.argv[1]
    
    # 1. Scraping
    run_step("scraper.py", [query])
    
    # 2. Enrichment
    run_step("enricher.py")
    
    # 3. Generation
    run_step("generator.py")
    
    # 4. Blasting (Conditional)
    # run_step("blaster.py")
    
    print("Workflow complete. Check data/leads.csv and proposals/drafts/")

if __name__ == "__main__":
    main()
