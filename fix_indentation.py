import os
import glob

def fix_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Start of with block
        if line.lstrip().startswith("with get_db_connection") and ":" in line:
            new_lines.append(line)
            with_indent = len(line) - len(line.lstrip())
            
            # The next line should be cursor = conn.cursor()
            if i + 1 < len(lines) and "cursor = conn.cursor()" in lines[i+1]:
                new_lines.append(lines[i+1])
                i += 2
                
                func_indent = with_indent - 4
                
                while i < len(lines):
                    curr_line = lines[i]
                    curr_stripped = curr_line.lstrip()
                    
                    if not curr_stripped:
                        new_lines.append(curr_line)
                    else:
                        curr_line_indent = len(curr_line) - len(curr_stripped)
                        if curr_line_indent <= func_indent and not curr_stripped.startswith("#") and not curr_stripped.startswith(")"):
                            # End of function
                            break
                        
                        # Add 4 spaces to everything to push it into the with block
                        if curr_line == "\n":
                            new_lines.append(curr_line)
                        else:
                            new_lines.append(" " * 4 + curr_line)
                            
                    i += 1
                continue
        
        new_lines.append(line)
        i += 1
        
    with open(filepath, 'w') as f:
        f.writelines(new_lines)

files = [
    "/home/openclaw/projects/1ai-reach/src/oneai_reach/api/v1/email_templates.py",
    "/home/openclaw/projects/1ai-reach/src/oneai_reach/api/v1/scheduled_messages.py",
    "/home/openclaw/projects/1ai-reach/src/oneai_reach/api/v1/broadcasts.py",
    "/home/openclaw/projects/1ai-reach/src/oneai_reach/api/v1/labels.py"
]

for f in files:
    fix_file(f)
    print(f"Fixed {f}")
