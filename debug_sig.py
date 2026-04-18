import sys
sys.path.insert(0, "src")
import inspect
from oneai_reach.api.v1.products import create_product

print(inspect.signature(create_product))
