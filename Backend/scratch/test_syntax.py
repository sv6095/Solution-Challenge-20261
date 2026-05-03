import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback

try:
    import agents.political_risk_agent
    import agents.tariff_risk_agent
    import agents.logistics_risk_agent
    print("Syntax checks passed!")
except SyntaxError as e:
    traceback.print_exc()
except Exception as e:
    traceback.print_exc()
