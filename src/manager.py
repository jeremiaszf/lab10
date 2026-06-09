"""Manager class for handling apartment management operations."""

from datetime import datetime

from src.models import (
    Apartment,
    ApartmentEvent,
    ApartmentSettlement,
    Bill,
    Parameters,
    Tenant,
    TenantBlacklistEntry,
    TenantSettlement,
    Transfer,
)


class Manager:
    """Manager class responsible for loading data and providing methods
    to manage apartments, tenants, transfers, bills, and apartment events.

    Attributes
    ----------
        parameters (Parameters): Configuration object containing file paths and validation limits.
        apartments (dict): A dictionary mapping apartment keys to Apartment objects.
        tenants (dict): A dictionary mapping tenant keys to Tenant objects.
        transfers (list): A list containing all Transfer objects.
        bills (list): A list containing all Bill objects.
        tenants_blacklist (list): A list of TenantBlacklistEntry objects representing blacklisted tenants.
        apartment_events (list): A list of ApartmentEvent objects tracking maintenance or issues.

    """

    def __init__(self, parameters: Parameters):
        self.parameters = parameters

        self.apartments = {}
        self.tenants = {}
        self.transfers = []
        self.bills = []
        self.tenants_blacklist = []
        self.apartment_events = []

        self.load_data()

    def load_data(self):
        """Load foundational data from JSON files specified in the parameters."""
        self.apartments = Apartment.from_json_file(self.parameters.apartments_json_path)
        self.tenants = Tenant.from_json_file(self.parameters.tenants_json_path)
        self.transfers = Transfer.from_json_file(self.parameters.transfers_json_path)
        self.bills = Bill.from_json_file(self.parameters.bills_json_path)
        self.tenants_blacklist = TenantBlacklistEntry.from_json_file(
            self.parameters.tenants_blacklist_json_path,
        )

    def load_additional_data(self):
        """Load additional dynamic data, such as apartment events, from JSON files."""
        self.apartment_events = ApartmentEvent.from_json_file(
            self.parameters.apartment_events_json_path,
        )

    def generate_apartment_events_report(
        self,
        apartment_key: str,
        only_unsolved: bool = True,
    ) -> list[ApartmentEvent]:
        """Generate a report of apartment events for a given apartment key.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment.
            only_unsolved (bool, optional): If True, filters out solved events. Defaults to True.

        Returns:
        -------
            List[ApartmentEvent]: A list of events matching the criteria for the specified apartment.

        """
        if apartment_key not in self.apartments:
            raise ValueError("Apartment key does not exist")
        return [
            event
            for event in self.apartment_events
            if event.apartment == apartment_key
            and (not event.solved or not only_unsolved)
        ]

    def check_tenants_apartment_keys(self) -> bool:
        """Check if all tenants have valid apartment keys that exist in the apartments data.

        Returns
        -------
            bool: True if all tenants are assigned to existing apartments, False otherwise.

        """
        for tenant in self.tenants.values():
            if tenant.apartment not in self.apartments:
                return False
        return True

    def get_apartment(self, apartment_key: str) -> Apartment | None:
        """Get an apartment object by its key.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment to retrieve.

        Returns:
        -------
            Apartment | None: The Apartment object if found, otherwise None.

        """
        return self.apartments.get(apartment_key, None)

    def get_apartment_costs(
        self,
        apartment_key: str,
        year: int = None,
        month: int = None,
    ) -> float | None:
        """Calculate the total costs for a given apartment, optionally filtered by year and month.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment.
            year (int, optional): The year for which to calculate costs. Defaults to None.
            month (int, optional): The month for which to calculate costs (1-12). Defaults to None.

        Returns:
        -------
            float | None: The total cost in PLN, or None if the apartment does not exist.

        """
        if month is not None and (month < 1 or month > 12):
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            return None
        total_cost = 0.0
        for bill in self.bills:
            if (
                bill.apartment == apartment_key
                and (year is None or bill.settlement_year == year)
                and (month is None or bill.settlement_month == month)
            ):
                total_cost += bill.amount_pln
        return total_cost

    def get_settlement(
        self,
        apartment_key: str,
        year: int,
        month: int,
    ) -> ApartmentSettlement | None:
        """Get the overall apartment settlement for a given apartment key, year, and month.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment.
            year (int): The settlement year.
            month (int): The settlement month (1-12).

        Returns:
        -------
            ApartmentSettlement | None: The settlement object, or None if the apartment doesn't exist or has no costs.

        """
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            return None
        total_cost = self.get_apartment_costs(apartment_key, year, month)
        if total_cost is None:
            return None

        return ApartmentSettlement(
            key=f"{apartment_key}-{year}-{month}",
            apartment=apartment_key,
            year=year,
            month=month,
            total_due_pln=total_cost,
        )

    def create_tenants_settlements(
        self,
        apartment_settlement: ApartmentSettlement,
    ) -> list[TenantSettlement] | None:
        """Create individual tenant settlements by dividing the total apartment cost evenly.

        Args:
        ----
            apartment_settlement (ApartmentSettlement): The main settlement object for the apartment.

        Returns:
        -------
            List[TenantSettlement] | None: A list of settlements for each tenant, or None if the apartment is invalid.

        """
        if apartment_settlement.month < 1 or apartment_settlement.month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_settlement.apartment not in self.apartments:
            return None
        tenants_in_apartment = [
            tenant
            for tenant in self.tenants.values()
            if tenant.apartment == apartment_settlement.apartment
        ]
        if not tenants_in_apartment:
            return []

        return [
            TenantSettlement(
                tenant=tenant.name,
                apartment_settlement=apartment_settlement.key,
                month=apartment_settlement.month,
                year=apartment_settlement.year,
                total_due_pln=apartment_settlement.total_due_pln
                / len(tenants_in_apartment),
            )
            for tenant in tenants_in_apartment
        ]

    def get_debtors(self, apartment_key: str, year: int, month: int) -> list[str]:
        """Get a list of tenant names (debtors) who have not fully paid their dues for a specific period.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment.
            year (int): The settlement year.
            month (int): The settlement month (1-12).

        Returns:
        -------
            List[str]: A list of names of tenants who are currently in debt.

        """
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        output = []
        settlement = self.get_settlement(apartment_key, year, month)
        tenant_settlements = self.create_tenants_settlements(settlement)

        for tenant_settlement in tenant_settlements:
            tenant_transfers = [
                transfer
                for transfer in self.transfers
                if self.tenants[transfer.tenant].name == tenant_settlement.tenant
                and transfer.settlement_year == year
                and transfer.settlement_month == month
            ]
            total_paid = sum(
                transfer.amount_pln
                for transfer in tenant_transfers
                if transfer.settlement_year == year
                and transfer.settlement_month == month
            )
            if total_paid < tenant_settlement.total_due_pln:
                output.append(tenant_settlement.tenant)
        return output

    def calculate_tax(self, year: int, month: int, tax_rate: float) -> float:
        """Calculate the tax amount based on the total income from transfers.

        Args:
        ----
            year (int): The year to calculate the tax for.
            month (int): The month to calculate the tax for.
            tax_rate (float): The applicable tax rate (e.g., 0.19 for 19%).

        Returns:
        -------
            float: The calculated tax amount rounded to the nearest integer.

        Example:
        -------
            >>> parameters = Parameters(max_transfer_pln=10000, max_refund_pln=2000, ...)
            >>> manager = Manager(parameters)
            >>> manager.calculate_tax(year=2023, month=5, tax_rate=0.19)
            450.0

        """
        total_income = sum(
            transfer.amount_pln
            for transfer in self.transfers
            if transfer.settlement_year == year and transfer.settlement_month == month
        )
        return round(total_income * tax_rate, 0)

    def check_deposits(self) -> float:
        """Check the global balance between total collected deposits and required deposit amounts.

        Returns
        -------
            float: The difference between collected deposits and required deposits.
                   A negative value means missing deposits.

        """
        total_deposits = 0.0
        total_due = 0.0
        for _, tenant in self.tenants.items():
            total_deposits += sum(
                transfer.amount_pln
                for transfer in self.transfers
                if self.tenants[transfer.tenant].name == tenant.name
                and transfer.type == "deposit"
            )
            total_due += tenant.deposit_pln

        return total_deposits - total_due

    def get_annual_balance(self, year: int) -> float:
        """Calculate the overall annual balance for a given year based on total income and total bills.

        Args:
        ----
            year (int): The year for which to calculate the balance.

        Returns:
        -------
            float: The annual balance (Income - Expenses).

        """
        total_income = sum(
            transfer.amount_pln
            for transfer in self.transfers
            if transfer.settlement_year == year
        )
        total_due = sum(
            bill.amount_pln for bill in self.bills if bill.settlement_year == year
        )
        return total_income - total_due

    def has_any_bills(self, apartment_key: str, year: int, month: int) -> bool:
        """Check if there are any recorded bills for a specific apartment and time period.

        Args:
        ----
            apartment_key (str): The unique identifier of the apartment.
            year (int): The year to check.
            month (int): The month to check (1-12).

        Returns:
        -------
            bool: True if at least one bill exists, False otherwise.

        """
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        if apartment_key not in self.apartments:
            raise ValueError("Apartment key does not exist")
        return any(
            bill
            for bill in self.bills
            if bill.apartment == apartment_key
            and bill.settlement_year == year
            and bill.settlement_month == month
        )

    def check_transfers_amount_range(self) -> bool:
        """Verify if all transfers have amounts within the allowed maximum limits specified in parameters.

        Returns
        -------
            bool: True if all transfers are within valid limits, False if any transfer exceeds them.

        """
        for transfer in self.transfers:
            if (
                transfer.amount_pln > self.parameters.max_transfer_pln
                or transfer.amount_pln < -self.parameters.max_refund_pln
            ):
                return False
        return True

    def check_tenant_blacklist(self, tenant_name: str) -> bool:
        """Check if a given tenant's name appears on the blacklist.

        Args:
        ----
            tenant_name (str): The name of the tenant to verify.

        Returns:
        -------
            bool: True if the tenant is blacklisted, False otherwise.

        """
        return any(
            entry for entry in self.tenants_blacklist if entry.tenant == tenant_name
        )

    def check_transfers_tenant(self) -> bool:
        """Validate that all transfers are associated with existing tenants and occur within their agreement dates.

        Returns
        -------
            bool: True if all transfers map to valid tenants and active dates, False otherwise.

        """
        for transfer in self.transfers:
            if transfer.tenant not in self.tenants:
                return False
            if (
                transfer.settlement_year is not None
                and transfer.settlement_month is not None
            ):
                agreement_from = self.tenants[transfer.tenant].date_agreement_from
                agreement_from = datetime.strptime(agreement_from, "%Y-%m-%d").date()
                agreement_to = self.tenants[transfer.tenant].date_agreement_to
                agreement_to = datetime.strptime(agreement_to, "%Y-%m-%d").date()
                if (transfer.settlement_year < agreement_from.year) or (
                    transfer.settlement_year > agreement_to.year
                ):
                    return False

        return True
