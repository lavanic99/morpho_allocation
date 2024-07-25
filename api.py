import requests

class ApiBA:
    def __init__(self, base_market_url, base_wallet_url, markets, target_wallet):
        self.base_market_url = base_market_url
        self.base_wallet_url = base_wallet_url
        self.markets = markets
        self.target_wallet = target_wallet
        self.data = []

    def fetch_wallet_supply(self, market_id):
        url = self.base_wallet_url.format(market_id)
        response = requests.get(url)
        if response.status_code == 200:
            wallets = response.json()['results']
            for wallet in wallets:
                if wallet['wallet_address'] == self.target_wallet:
                    return wallet['supply']
        return 0  # Return 0 if the wallet is not found or request fails

    def fetch_data(self):
        for market in self.markets:
            market_url = self.base_market_url.format(market)
            market_response = requests.get(market_url)
            if market_response.status_code == 200:
                market_data = market_response.json()[0]
                maker_allocation = self.fetch_wallet_supply(market)
                
                combined_data = {
                    "market": market,
                    "total_supply": market_data["total_supply"],
                    "utilization": market_data["utilization"],
                    "borrow_rate": market_data["borrow_rate_apy"],
                    "maker_allocation": maker_allocation
                }
                self.data.append(combined_data)
            else:
                print(f"Failed to fetch data for market {market}")

        return self.data