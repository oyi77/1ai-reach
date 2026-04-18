import sys
sys.path.insert(0, "src")
from oneai_reach.api.v1.products import router

for route in router.routes:
    if "POST" in route.methods:
        for dep in route.dependant.dependencies:
            print("Dependency:", dep.name)
        for param in route.dependant.body_params:
            print("Body param:", param.name)
