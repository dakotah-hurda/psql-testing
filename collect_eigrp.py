import os
import socket
import psycopg

from dotenv import load_dotenv
from netmiko import ConnectHandler

class eigrp_speaker():
    def __init__(self,ip):
        self.ip = ip
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
        except:
            self.ssh_state = False
            self.eigrp_data = dict()
            self.hostname = None
            self.eigrp_neighbors = list()
    
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
        # Open a cursor to perform database operations
        with conn.cursor() as cur:

            # Add the rtr to inventory if it doesn't already exist.
            cur.execute(
                """
                INSERT INTO inventory (ip, hostname, dns_name, discovered_state, ssh_state)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ip) 
                DO UPDATE SET
                    hostname = EXCLUDED.hostname,
                    dns_name = EXCLUDED.dns_name,
                    discovered_state = EXCLUDED.discovered_state,
                    ssh_state = EXCLUDED.ssh_state;
                """,
                (rtr.ip, rtr.hostname, rtr.dns_name, True, rtr.ssh_state)
            )

            # Loop through all the rtr's learned neighbors...
            for nei in rtr.eigrp_neighbors:
                # add the neighbor to inventory if it doesn't exist yet
                cur.execute(
                    """
                    INSERT INTO inventory (ip, discovered_state) 
                    VALUES (%s, %s)
                    ON CONFLICT (ip) DO NOTHING;
                    """, 
                    (nei, False)
                )                    
                
                # Create rtr --> nei relationship.
                # Also adds learned prefixes from the nei to DB.
                # Override previous data ON CONFLICT because this is
                # the actual live data as seen from the rtr's perspective.
                cur.execute(
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
            conn.commit()

def iterate_discovery(conn):
    # Begins dynamic discovery by referencing DB data
    discovery_active = True # loop control
    while discovery_active:
        
        pending_routers = list()

        with conn.cursor() as cur:
            # Collects all data from inventory table
            cur.execute("""
                SELECT (ip, discovered_state) FROM inventory;
                """)

            rows = cur.fetchall()

            # Checks if router has been marked discovered yet
            
            for row in rows:
                if row[0][1] != 't':
                    print(f"Router isn't discovered yet: {row[0][0]}")
                    pending_routers.append(row[0][0])
                    continue
                else:
                    print(f"Router has been previously discovered: {row[0][0]}")
                    continue
            
            if len(pending_routers) > 0:
                print("Total number routers pending discovery (this iteration): " + str(len(pending_routers)))
                for ip in pending_routers:
                    print(f"Beginning discovery on {ip}...")
                    rtr = eigrp_speaker(ip)
                    print(f"Discovery functions completed on {ip}. Posting results to DB.")
                    inventory_to_db(conn, rtr)
                    print(f"Database post complete.")

            elif len(pending_routers) == 0:
                print("No routers marked for discovery.")
                discovery_active = False

        # Iterate through all non-discovered routers and discover their neighbors
        # add neighbors to DB
        # set discovery_active to False when no further iterations exist

def main():
    PG_USER = os.environ.get("PG_USER")
    PG_PASS = os.environ.get("PG_PASS")
    HOSTNAME = "localhost"
    PORT = "5432"
    DB_NAME = "routers"
    SEED_IP = "172.16.1.3"
    # ips = ["172.16.1.3", "172.16.1.5", "172.21.1.26", "10.11.11.2", "172.21.1.18", "172.16.2.38", "172.16.1.253", "172.16.4.2", "172.20.3.1", "172.21.1.14", "172.21.1.22", "172.17.2.6", "172.16.2.61"]

    with psycopg.connect(f"postgresql://{PG_USER}:{PG_PASS}@{HOSTNAME}:{PORT}/{DB_NAME}") as conn:
        try: create_db_tables(conn)
        except Exception as e: 
            print(f"Failed to initialize DB tables: {e}")

        rtr = eigrp_speaker(SEED_IP)
        inventory_to_db(conn, rtr)

        iterate_discovery(conn)
        
if __name__ == '__main__':
    load_dotenv()
    main()