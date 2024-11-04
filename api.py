import requests

class ApiBA:
    def __init__(self, base_market_url, base_wallet_url, markets, target_wallet, vaults_url, ssr_url):
        # This method now accepts 5 arguments plus self
        self.base_market_url = base_market_url
        self.base_wallet_url = base_wallet_url
        self.markets = markets
        self.target_wallet = target_wallet
        self.vaults_url = vaults_url
        self.ssr_url = ssr_url
        self.data = []

    def fetch_wallet_supply(self, market_id):
        url = self.base_wallet_url.format(market_id)
        response = requests.get(url)
        if response.status_code == 200:
            wallets = response.json()['results']
            for wallet in wallets:
                if wallet['wallet_address'] == self.target_wallet:
                    return wallet['supply']
        return 0

    def fetch_vault_caps(self):
        response = requests.get(self.vaults_url)
        if response.status_code == 200:
            return {item['market_uid']: item['cap'] for item in response.json()['results']}
        return {}

    def fetch_ssr_rate(self):
        # New method to fetch SSR rate
        response = requests.get(self.ssr_url)
        if response.status_code == 200:
            return response.json().get("ssr_rate")
        return None

    def fetch_data(self):
        vault_caps = self.fetch_vault_caps()
        ssr_rate = self.fetch_ssr_rate()

        for market in self.markets:
            market_url = self.base_market_url.format(market)
            market_response = requests.get(market_url)
            if market_response.status_code == 200:
                market_data = market_response.json()[0]
                maker_allocation = self.fetch_wallet_supply(market)
                cap = vault_caps.get(market, None)
                
                combined_data = {
                    "market": market,
                    "total_supply": market_data["total_supply"],
                    "utilization": market_data["utilization"],
                    "borrow_rate": market_data["borrow_rate_apy"],
                    "maker_allocation": maker_allocation,
                    "supply_cap": cap,
                    "ssr_rate": ssr_rate
                }
                self.data.append(combined_data)
            else:
                print(f"Failed to fetch data for market {market}")

        return self.data