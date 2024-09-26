class PoolDataHandler:
    def __init__(self, pools_df, market_to_pool):
        self.pools_df = pools_df
        self.market_to_pool = market_to_pool

    def extract_lltv(self, pool_key):
        # Extract the percentage number and convert to float
        try:
            parts = pool_key.split()
            if len(parts) > 1:
                lltv = float(parts[1].replace('%', '')) / 100
            else:
                lltv = 0.0
        except ValueError:
            lltv = 0.0
        return lltv

    def populate_dataframe(self, data):
        for market_data in data:
            pool_key = self.market_to_pool[market_data['market']]
            self.pools_df.loc[pool_key, 'Total Supply'] = int(round(float(market_data['total_supply']), 0))
            self.pools_df.loc[pool_key, 'Maker Allocation'] = int(round(float(market_data['maker_allocation']), 0))
            self.pools_df.loc[pool_key, 'Utilization'] = round(float(market_data['utilization']), 4)
            self.pools_df.loc[pool_key, 'Borrow Rate'] = round(float(market_data['borrow_rate']), 4)
            self.pools_df.loc[pool_key, 'LLTV'] = float(self.extract_lltv(pool_key))  # Populate LLTV based on the pool key
            self.pools_df.loc[pool_key, 'Supply Cap'] = int(round(float(market_data['supply_cap']), 0))
            self.pools_df.loc[pool_key, 'DSR'] = round(float(market_data['dsr_rate']), 4)
        print("\nUpdated DataFrame:")
        return self.pools_df


# Class for data manipulation and analysis of the pools
class PoolAnalysis:
    def __init__(self, pool_df, idle_df, realloc_metaparm):
        self.pool_df = pool_df
        self.idle_df = idle_df
        self.total_maker_allocation = self.pool_df['Maker Allocation'].sum()
        self.total_vault_size = idle_df['Maker Allocation'].iloc[0] + self.pool_df['Maker Allocation'].sum()
        self.inactive_min_balance = realloc_metaparm['inactive_pool']['min_balance']
        self.inactive_max_utilization = realloc_metaparm['inactive_pool']['max_utilization']
        self.inactive_max_portion_to_withdraw = realloc_metaparm['inactive_pool']['max_portion_to_withdraw']
        self.inactive_allocation_significance_threshold = realloc_metaparm['inactive_pool']['allocation_significance_threshold']
        self.active_min_balance = realloc_metaparm['active_pool']['min_balance']
        self.active_max_utilization = realloc_metaparm['active_pool']['max_utilization']
        self.active_max_portion_to_withdraw = realloc_metaparm['active_pool']['max_portion_to_withdraw']
        self.active_allocation_significance_threshold = realloc_metaparm['active_pool']['allocation_significance_threshold']
        self.yes_funds = True

    # In a case we want to manually input values for a pool
    def input_values_for_pool(self, pool_df, pool_key):
        print(f"\nPlease input values for the {pool_key} pool:")
        
        while True:
            status_input = input(f"Enter the 'Status' (Active/Inactive) for {pool_key}: ")
            if status_input in ['Active', 'Inactive']:
                pool_df.loc[pool_key, 'Status'] = status_input
                break
            else:
                print("Error: The status must be 'Active' or 'Inactive'!")
        
        numerical_columns = ['LLTV', 'Total Supply', 'Maker Allocation', 'Utilization', 'Borrow Rate']
        for column in numerical_columns:
            while True:
                try:
                    value_input = input(f"Enter the '{column}' for {pool_key}: ")
                    if column in ['Utilization', 'Borrow Rate', 'LLTV']:
                        value = float(value_input)
                        if 0 <= value <= 100: # Check if the value is within a range [0, 100]
                            pool_df.loc[pool_key, column] = value / 100  # Convert to a decimal
                            break
                        else:
                            print("Error: The value must be between 0 and 100 (as percentage).")
                    else:
                        value = float(value_input)
                        if value >= 0:
                            pool_df.loc[pool_key, column] = value
                            break
                        else:
                            print("Error: The value must be a non-negative number.")
                except ValueError:
                    print("Error: Please enter a valid number.")
    
    def calculate_target_borrow_rate(self, row):
        return round(max(
            row['DSR'] + row['Fixed Spread'] + self.total_vault_size * row['Fixed Slope'],
            row['DSR'] * (1 + row['Proportional Spread']) * (1 + row['Proportional Slope'] * self.total_vault_size)), 4)
    
    def calculate_min_borrow_rate(self, row):
        return round(row['Target Borrow Rate'] * row['Low Target Threshold'], 4)
    
    def calculate_max_borrow_rate(self, row):
        return round(row['Target Borrow Rate'] * row['High Target Threshold'], 4)
    
    def calculate_total_borrow(self, row):
        return int(row['Total Supply'] * row['Utilization'])

    def calculate_maker_borrow(self, row):
        return int(row['Total Borrow'] * (row['Maker Allocation'] / row['Total Supply']))

    def calculate_optimal_rate(self, row):
        if row['Utilization'] > 0.9:
            return round(row['Borrow Rate'] / (30 * row['Utilization'] - 26), 4)
        else:
            return round(row['Borrow Rate'] / (0.25 + (5/6) * row['Utilization']), 4)
        
    def calculate_capped_borrow_rate(self, row):
        return round(min(row['Borrow Rate'], row['Optimal Rate']), 4)
    
    def calculate_utilization_where_rate_equal_to_dsr(self, row):
        if row['Optimal Rate'] < row['DSR']:
            result = ((row['DSR'] / row['Optimal Rate']) + 26) / 30
        else:
            result = 1.2 * ((row['DSR'] / row['Optimal Rate']) - 0.25)
        return round(min(result, 1), 4)
    
    def calculate_dsr_adjustment(self, row, min_balance):
        return int(min(max(
            row['Total Borrow'] / row['Utilization Where Rate Equal to DSR'] - row['Total Supply'], 
            -row['Maker Allocation'], 
            min_balance - row['Total Supply']), 0))
    
    def calculate_total_supply_after_dsr_adjustment(self, row):
        return int(row['Total Supply'] + row['DSR Adjustment'])
    
    def calculate_maker_supply_after_dsr_adjustment(self, row):
        return int(row['Maker Allocation'] + row['DSR Adjustment'])
    
    def calculate_utilization_after_dsr_adjustment(self, row):
        return round(row['Total Borrow'] / row['Total Supply After DSR Adjustment'], 4)
    
    def calculate_inactive_withdrawals(self, row, min_balance, max_utilization, withdrawal_portion):
        if row['Status'] == "Inactive":
            adjustment = min(
                max(
                    min_balance - row['Total Supply After DSR Adjustment'], 
                    (row['Total Borrow'] / max_utilization) - row['Total Supply After DSR Adjustment'], 
                    -row['Maker Supply After DSR Adjustment'], 
                    -row['DSR Adjustment'] - (row['Total Supply'] * withdrawal_portion)
                    ), 
                0)
            
            return int(adjustment)
        else:
            return 0
        
    def calculate_utilization_where_rate_equal_to_min_target(self, row):
        if row['Optimal Rate'] < row['Min Borrow Rate']:
            result = ((row['Min Borrow Rate'] / row['Optimal Rate']) + 26) / 30
        else:
            result = 1.2 * ((row['Min Borrow Rate'] / row['Optimal Rate']) - 0.25)
        return round(min(result, 1), 4)
    
    def calculate_active_withdrawals(self, row, yes_active_funds, min_balance, max_utilization, withdrawal_portion):
        if yes_active_funds and row['Status'] == "Active":
            adjustment = min(max((row['Total Borrow'] / max_utilization) - row['Total Supply'] -row['DSR Adjustment'],
                                -row['Maker Supply After DSR Adjustment'], 
                                -row['DSR Adjustment'] - (row['Total Supply'] * withdrawal_portion), 
                                min_balance - row['Total Supply After DSR Adjustment'], 
                                row['Total Borrow'] / row['Utilization Where Rate Equal To Min Target'] - row['Total Supply After DSR Adjustment']), 0)
            
            return int(adjustment)
        else:
            return 0
        
    def calculate_utilization_where_rate_equal_to_max_target(self, row):
        if row['Optimal Rate'] < row['Max Borrow Rate']:
            result = ((row['Max Borrow Rate'] / row['Optimal Rate']) + 26) / 30
        else:
            result = 1.2 * ((row['Max Borrow Rate'] / row['Optimal Rate']) - 0.25)
        return round(min(result, 1), 4)
    
    def calculate_active_deposits(self, row):
        if row['Status'] == "Active":
            return max(min(row['Total Borrow'] / row['Utilization Where Rate Equal To Max Target'] - row['Total Supply After DSR Adjustment'], 
                               row['Supply Cap'] - row['Maker Supply After DSR Adjustment']), 
                               0)
        else:
            return 0

        
    def calculate_manual_adjustment(self, row):
        # Here you can define the logic for manual adjustment if there's any rule-based approach.
        # If it's completely manual, then you may want to ask for user input.
        return 0 
    
    def calculate_total_change(self, row):
        total_sum = row['DSR Adjustment'] + row['Inactive Withdrawal'] + row['Active Withdrawal'] + row['Active Deposits'] + row['Manual Adjustment']

        if -10000 <= total_sum <= 10000:
            return 0
        else:
            return total_sum

    def calculate_final_allocation(self, row):
        return int(row['Maker Allocation'] + row['Total Change'])

    def calculate_final_supply(self, row):
        return int(row['Total Supply'] + row['Total Change'])

    def calculate_final_utilization(self, row):
        return round(row['Total Borrow'] / row['Final Supply'], 4)

    def calculate_final_borrow_rate(self, row):
        if row['Final Utilization'] < 0.9:
            return round(0.25 * row['Optimal Rate'] + (5/6) * row['Final Utilization'] * row['Optimal Rate'], 4)
        else:
            return round(30 * row['Optimal Rate'] * row['Final Utilization'] - 26 * row['Optimal Rate'], 4)
        
    def calculate_final_capped_rate(self, row):
        return min(row['Final Borrow Rate'], row['Optimal Rate'])
    
    def calculate_maker_borrow_at_old_utilization(self, row):
        return int(row['Final Allocation'] * row['Utilization'])

    def calculate_borrow_rate_change(self, row):
        return row['Final Borrow Rate'] - row['Borrow Rate']
    
    def define_active_or_inactive(self):
        # Convert the 'Status' column to a string type to accommodate 'Active'/'Inactive' values
        if 'Status' not in self.pool_df.columns or self.pool_df['Status'].dtype != 'object':
            self.pool_df['Status'] = self.pool_df['Status'].astype('object')
            
        print("Please enter 'Active' or 'Inactive' for each market:")
        for index in self.pool_df.index:
            # Loop to ensure valid input
            while True:
                status = input(f"Status for {index} (Active/Inactive): ").strip()
                if status in ['Active', 'Inactive']:
                    self.pool_df.loc[index, 'Status'] = status
                    break
                else:
                    print("Invalid input. Please enter 'Active' or 'Inactive'.")

        print("\nUpdated DataFrame with Status:")

    def update_pool_dataframe(self):
        for index, row in self.pool_df.iterrows():
            row['Total Borrow'] = self.calculate_total_borrow(row)
            row['Maker Borrow'] = self.calculate_maker_borrow(row)
            row['Optimal Rate'] = self.calculate_optimal_rate(row)
            row['Capped Borrow Rate'] = self.calculate_capped_borrow_rate(row)

#            row['DSR'] = round(0.0600, 4)

            row['Target Borrow Rate'] = self.calculate_target_borrow_rate(row)

            row['Min Borrow Rate'] = self.calculate_min_borrow_rate(row)

            row['Max Borrow Rate'] = self.calculate_max_borrow_rate(row)

            row['Utilization Where Rate Equal to DSR'] = self.calculate_utilization_where_rate_equal_to_dsr(row)

            row['DSR Adjustment'] = self.calculate_dsr_adjustment(row, self.inactive_min_balance)
            row['Total Supply After DSR Adjustment'] = self.calculate_total_supply_after_dsr_adjustment(row)
            row['Maker Supply After DSR Adjustment'] = self.calculate_maker_supply_after_dsr_adjustment(row)
            row['Utilization After DSR Adjustment'] = self.calculate_utilization_after_dsr_adjustment(row)
            
            row['Inactive Withdrawal'] = self.calculate_inactive_withdrawals(row, self.inactive_min_balance, self.inactive_max_utilization, self.inactive_max_portion_to_withdraw)
            row['Utilization Where Rate Equal To Min Target'] = self.calculate_utilization_where_rate_equal_to_min_target(row)

            row['Active Withdrawal'] = self.calculate_active_withdrawals(row, self.yes_funds, self.active_min_balance, self.active_max_utilization, self.active_max_portion_to_withdraw)
            row['Utilization Where Rate Equal To Max Target'] = self.calculate_utilization_where_rate_equal_to_max_target(row)
            row['Active Deposits'] = self.calculate_active_deposits(row)
            row['Manual Adjustment'] = self.calculate_manual_adjustment(row)
            row['Total Change'] = self.calculate_total_change(row)
            
            row['Final Allocation'] = self.calculate_final_allocation(row)
            row['Final Supply'] = self.calculate_final_supply(row)
            row['Final Utilization'] = self.calculate_final_utilization(row)
            
            row['Final Borrow Rate'] = self.calculate_final_borrow_rate(row)
            row['Final Capped Rate'] = self.calculate_final_capped_rate(row)
            row['Maker Borrow at Old Utilization'] = self.calculate_maker_borrow_at_old_utilization(row)
            row['Borrow Rate Change'] = self.calculate_borrow_rate_change(row)
            
            self.pool_df.loc[index] = row

        return self.pool_df

    @staticmethod
    def color_net_change(value):
        if value < 0:
            color = 'red'
        elif value > 0:
            color = 'green'
        else:
            color = 'black'
        return 'color: %s' % color

# Class for getting statistics of the pools
class PoolOverview:
    def __init__(self, pool_df, pool_overview):
        self.pool_df = pool_df
        self.pool_overview = pool_overview

    def update_total_non_idle_allocation(self, pool_df, pool_overview):
        total_non_idle_allocation = pool_df['Maker Allocation'].sum()
        future_total_non_idle_allocation = pool_df['Final Allocation'].sum()

        pool_overview.at['Total Non-Idle Allocation', 'Current'] = total_non_idle_allocation
        pool_overview.at['Total Non-Idle Allocation', 'Future'] = future_total_non_idle_allocation

        return pool_overview
    
    def update_supply_weighted_lltv(self, pool_df, pool_overview):
        supply_weighted_lltv = (pool_df['Maker Allocation'] * pool_df['LLTV']).sum() / pool_df['Maker Allocation'].sum()
        future_supply_weighted_lltv = (pool_df['Final Allocation'] * pool_df['LLTV']).sum() / pool_df['Final Allocation'].sum()

        pool_overview.at['Supply Weighted LLTV', 'Current'] = supply_weighted_lltv
        pool_overview.at['Supply Weighted LLTV', 'Future'] = future_supply_weighted_lltv

        return pool_overview
    
    def update_supply_weighted_sUSDe(self, pool_df, pool_overview):
        filtered_df = pool_df[pool_df.index.str.startswith('sUSDe')]

        supply_weighted_sUSDe = filtered_df['Maker Allocation'].sum() / pool_df['Maker Allocation'].sum()
        future_supply_weighted_sUSDe = filtered_df['Final Allocation'].sum() / pool_df['Final Allocation'].sum()

        pool_overview.at['Supply Weighted sUSDe', 'Current'] = supply_weighted_sUSDe
        pool_overview.at['Supply Weighted sUSDe', 'Future'] = future_supply_weighted_sUSDe

        return pool_overview

    def update_avg_borrow_rate(self, pool_df, pool_overview):
        avg_borrow_rate = (pool_df['Maker Borrow'] * pool_df['Borrow Rate']).sum() / pool_df['Maker Borrow'].sum()
        future_avg_borrow_rate = (pool_df['Maker Borrow'] * pool_df['Final Borrow Rate']).sum() / pool_df['Maker Borrow'].sum()

        pool_overview.at['Average Borrow Rate', 'Current'] = avg_borrow_rate
        pool_overview.at['Average Borrow Rate', 'Future'] = future_avg_borrow_rate

        return pool_overview
    
    def update_avg_capped_rate(self, pool_df, pool_overview):
        avg_capped_rate = (pool_df['Maker Borrow'] * pool_df['Capped Borrow Rate']).sum() / pool_df['Maker Borrow'].sum()
        future_avg_capped_rate = (pool_df['Maker Borrow'] * pool_df['Final Capped Rate']).sum() / pool_df['Maker Borrow'].sum()

        pool_overview.at['Average Capped Rate', 'Current'] = avg_capped_rate
        pool_overview.at['Average Capped Rate', 'Future'] = future_avg_capped_rate

        return pool_overview

    def update_rate_at_prior_equilibrium(self, pool_df, pool_overview):
        rate_at_prior_equilibrium = (pool_df['Maker Borrow'] * pool_df['Borrow Rate']).sum() / pool_df['Maker Borrow'].sum()
        future_rate_at_prior_equilibrium = (pool_df['Maker Borrow'] * pool_df['Final Borrow Rate']).sum() / pool_df['Maker Borrow'].sum()

        pool_overview.at['Rate at Prior Equilibrium', 'Current'] = rate_at_prior_equilibrium
        pool_overview.at['Rate at Prior Equilibrium', 'Future'] = future_rate_at_prior_equilibrium

        return pool_overview

    def compute_change(self, pool_overview):
        pool_overview['Change'] = pool_overview.apply(
            lambda row: (row['Future'] - row['Current']) / row['Current'] if row['Current'] != 0 else None, axis=1)
        return pool_overview
    
    def update_pool_overview(self):
        pool_overview = self.update_total_non_idle_allocation(self.pool_df, self.pool_overview)
        pool_overview = self.update_supply_weighted_lltv(self.pool_df, self.pool_overview)
        pool_overview = self.update_supply_weighted_sUSDe(self.pool_df, self.pool_overview)
        pool_overview = self.update_avg_borrow_rate(self.pool_df, self.pool_overview)
        pool_overview = self.update_avg_capped_rate(self.pool_df, self.pool_overview)
        pool_overview = self.update_rate_at_prior_equilibrium(self.pool_df, self.pool_overview)
        pool_overview = self.compute_change(self.pool_overview)
        
        return pool_overview