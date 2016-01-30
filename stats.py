import time

class SMSStats:
    def __init__(self, dbconn):
        self.dbconn = dbconn

    def log_incoming_message(self, sender, contents):
        try:
            c = self.dbconn.cursor()
            c.execute(
                "insert into smslog (timestamp, sender, contents, direction)"
                " values(?, ?, ?, ?)",
                (
                    int(time.time()),
                    sender,
                    contents,
                    'IN'
                )
            )
            return True
        except Exception as e:
            return False

    def log_outgoing_message(self, sender, recipient, contents, count):
        try:
            c = self.dbconn.cursor()
            c.execute(
                "insert into smslog (timestamp, sender, recipient, contents, direction, sms_count)"
                " values(?, ?, ?, ?, ?, ?)",
                (
                    int(time.time()),
                    sender,
                    recipient,
                    contents,
                    'OUT',
                    count
                )
            )
            return True
        except Exception as e:
            return False

    def get_statistics(self):
        count_total_in = None
        count_total_out = None

        c = self.dbconn.cursor()
        for row in c.execute("select count(*) from smslog where direction = 'IN'"):
            count_total_in = row[0]

        for row in c.execute("select sum(sms_count) from smslog where direction = 'OUT'"):
            count_total_out = row[0]

        return {
            'total_in': count_total_in,
            'total_out': count_total_out
        }

