import sys
sys.path.insert(0, "src")
from oneai_reach.api.v1.products import router

for route in router.routes:
    if "POST" in route.methods:
        print("Fields:")
        for param in route.dependant.body_params:
            print(" -", param.name)
