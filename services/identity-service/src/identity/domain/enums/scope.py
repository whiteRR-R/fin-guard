from enum import Enum


class MachineScope(Enum):
    TRANSACTIONS_WRITE = "transactions:write"
    TRANSACTIONS_READ = "transactions:read"
    RISK_RESULTS_READ = "risk-results:read"
    WEBHOOKS_MANAGE = "webhooks:manage"
