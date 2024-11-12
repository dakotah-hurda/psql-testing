import os
import socket
import psycopg

from dotenv import load_dotenv
from netmiko import ConnectHandler

class EIGRPSpeaker():
    def __init__(self,ip):
        self.ip = str(ip)
        self.dns_name = self.dns_record(ip)
        conn_data = {
            'device_type': 'cisco_ios',
            'host': self.ip,
            'username': os.environ.get("SSH_USER"),
            'password': os.environ.get("SSH_PASS"),
            'conn_timeout': 3,
            'auth_timeout': 5
        }

        try: 
            self.ssh_connection = ConnectHandler(**conn_data)
            self.ssh_state = True
            self.hostname = self.collect_hostname(self.ssh_connection)
            self.eigrp_neighbors = self.collect_eigrp_neighbors(self.ssh_connection)
            self.rx_prefixes = self.collect_rx_prefixes(self.ssh_connection, self.eigrp_neighbors)
        except Exception as e:
            print(f"Error collecting information from {ip}:\n\n {e}")
            self.ssh_state = False
            self.eigrp_data = dict()
            self.hostname = None
            self.eigrp_neighbors = list()
            self.rx_prefixes = list()
    
    def collect_hostname(self, ssh_connection):
        try: 
            hostname = ssh_connection.send_command("show run | i hostname").split(" ")[1]
                
        except Exception as e: 
            try: hostname = ssh_connection.send_command("show run | include switchname").split(" ")[1]
            except Exception as e:
                hostname = ""
                print(f"Error found while collecting hostname from: {ssh_connection.host}")
                print(e)
        
        return hostname

    def collect_eigrp_neighbors(self, ssh_connection):
        try: 
            output = ssh_connection.send_command("show ip eigrp neighbors", use_textfsm=True)
        except Exception as e:
            raise
        
        eigrp_neighbors = list()
        for nei in output:
            eigrp_neighbors.append(nei['ip_address'])
        
        return eigrp_neighbors

    def collect_rx_prefixes(self, ssh_connection, eigrp_neighbors) -> dict:
        eigrp_topology = ssh_connection.send_command("sh ip eigrp topology", use_textfsm=True)
        rx_prefixes = dict()
        for nei in eigrp_neighbors:
            rx_prefixes[nei] = list()
        
        for adv in eigrp_topology:
            pfx = f"{adv['network']}/{adv['prefix_length']}"
            for nei in eigrp_neighbors:
                if nei in adv['adv_router']:
                    rx_prefixes[nei].append(pfx)
        
        return rx_prefixes

    def dns_record(self, ip):
        try: dns_name = socket.gethostbyaddr(ip)[0]
        except: dns_name = "NOTFOUND"

        return dns_name

def create_db_tables(conn):
    with conn.cursor() as cur:

            # Creates inventory table if it does not exist. 
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    ip INET PRIMARY KEY,
                    hostname VARCHAR(255),
                    dns_name VARCHAR(255),
                    num_prefixes INT,
                    num_neighbors INT,
                    discovered_state BOOL,
                    ssh_state BOOL
                );
                """)

            # Creates eigrp_neighbors table if it does not exist. 
            cur.execute("""
                CREATE TABLE IF NOT EXISTS router_neighbors (
                    router_id INET REFERENCES inventory(ip) ON DELETE CASCADE,
                    neighbor_id INET REFERENCES inventory(ip) ON DELETE CASCADE,
                    learned_prefixes CIDR[],
                    PRIMARY KEY (router_id, neighbor_id)
                );
                """)

def inventory_to_db(conn, rtr):
    
    def inventory_router(cursor, rtr):
        """
        Inserts or updates a router in the inventory table.
        
        Parameters:
            cursor (psycopg cursor): Database cursor for executing queries.
            rtr (EIGRPSpeaker): Router object containing router details.
        """
        cursor.execute(
            """
            INSERT INTO inventory (
                ip, hostname, dns_name, num_prefixes, num_neighbors, 
                discovered_state, ssh_state
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ip) 
            DO UPDATE SET
                hostname = EXCLUDED.hostname,
                dns_name = EXCLUDED.dns_name,
                num_prefixes = EXCLUDED.num_prefixes,
                num_neighbors = EXCLUDED.num_neighbors,
                discovered_state = EXCLUDED.discovered_state,
                ssh_state = EXCLUDED.ssh_state;
            """,
            (
                rtr.ip,
                rtr.hostname,
                rtr.dns_name,
                len(rtr.rx_prefixes) if rtr.rx_prefixes else 0,  # Number of prefixes
                len(rtr.eigrp_neighbors),                 # Number of neighbors
                True,                                             # Discovered state
                rtr.ssh_state                                     # SSH state
            )
        )

    def inventory_rtr_neighbors(cursor, rtr):
        # Loop through all the rtr's learned neighbors...
        for nei in rtr.eigrp_neighbors:
            # add the neighbor to inventory if it doesn't exist yet
            cursor.execute(
                """
                INSERT INTO inventory (ip, discovered_state) 
                VALUES (%s, %s)
                ON CONFLICT (ip) DO NOTHING;
                """, 
                (nei, False)
            )                    
    def import_rtr_adjacencies(cursor, rtr):
        # Create rtr --> nei relationship.
        # Also adds learned prefixes from the nei to DB.
        # Override previous data ON CONFLICT because this is
        # the actual live data as seen from the rtr's perspective.
        for nei in rtr.eigrp_neighbors:
            cursor.execute(
                """
                INSERT INTO router_neighbors 
                (router_id, neighbor_id, learned_prefixes)
                VALUES (%s, %s, %s)
                ON CONFLICT (router_id, neighbor_id) DO 
                UPDATE SET
                    router_id = EXCLUDED.router_id,
                    neighbor_id = EXCLUDED.neighbor_id,
                    learned_prefixes = EXCLUDED.learned_prefixes
                ;
                """,
                (rtr.ip, nei, rtr.rx_prefixes[nei])
            )

            # Below section adds an implied bidi relationship, but I could just simplify logic and rely
            # on the above code. Hmm. What's cleaner? It seems better to always add the two-way relationship,
            # but then I have to rely on SQL logic to only UPSERT when it makes sense.

            # # ...and create the nei --> rtr relationship (reverse).
            # # We could try to add 'learned_prefixes' here, 
            # # but it makes more sense to learn it from the 
            # # remote router's perspective on a subsequent cycle
            # # with the SQL statement above.
            # cur.execute(
            #     """
            #     INSERT INTO router_neighbors (router_id, neighbor_id)
            #     VALUES (%s, %s)
            #     ON CONFLICT (router_id, neighbor_id) DO NOTHING;
            #     """,
            #     (nei, rtr.ip)
            # )

        # Make the changes to the database persistent
    
    with conn.cursor() as cursor:
        inventory_router(cursor, rtr) # Add router to DB
        inventory_rtr_neighbors(cursor, rtr) # Add router's neighbors to DB
        import_rtr_adjacencies(cursor, rtr)#  Add router's EIGRP adjacencies to DB

    conn.commit()

def iterate_discovery(conn):
    discovery_active = True  # Control variable for the loop

    while discovery_active:
        with conn.cursor() as cur:
            # Select all undiscovered routers
            cur.execute("SELECT ip FROM inventory WHERE discovered_state IS FALSE;")
            pending_routers = [row[0] for row in cur.fetchall()]

        # If there are no more undiscovered routers, exit the loop
        if not pending_routers:
            discovery_active = False
            print("No more routers pending discovery.")
            break

        # Process each router in the list of pending routers
        for ip in pending_routers:
            print(f"Discovering {ip}")
            rtr = EIGRPSpeaker(ip)
            inventory_to_db(conn, rtr)
        
        # Optional: Add a delay here if desired to prevent rapid looping

def main():
    PG_USER = os.environ.get("PG_USER")
    PG_PASS = os.environ.get("PG_PASS")
    HOSTNAME = "localhost" # PSQL server
    PORT = "5432" # PSQL connection
    DB_NAME = "routers"
    SEED_IP = "172.16.1.3" # First router to start the "crawl" with

    with psycopg.connect(f"postgresql://{PG_USER}:{PG_PASS}@{HOSTNAME}:{PORT}/{DB_NAME}") as conn:
        try: create_db_tables(conn)
        except Exception as e: 
            print(f"Failed to initialize DB tables: {e}")

        rtr = EIGRPSpeaker(SEED_IP)
        inventory_to_db(conn, rtr)

        iterate_discovery(conn)
        
if __name__ == '__main__':
    load_dotenv()
    main()