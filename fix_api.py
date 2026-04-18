import sys
sys.path.insert(0, "src")
from fastapi import Body
from oneai_reach.api.v1.products import router

for route in router.routes:
    if "POST" in route.methods:
        print(route.name, route.path)
        if hasattr(route, "body_field") and route.body_field:
            print("body_field:", route.body_field.name)
            print("embed:", getattr(route.body_field.field_info, "embed", None))
