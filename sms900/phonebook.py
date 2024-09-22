import re

import sqlite3

class SMS900InvalidAddressbookEntry(Exception):
    pass

class PhoneBook:
    def __init__(self, dbconn):
        self.dbconn = dbconn

    def add_number(self, nickname, number):
        nickname = self._get_valid_nickname(nickname)

        # Assume number has been canonicalized
        try:
            c = self.dbconn.cursor()
            c.execute('insert into phonebook(nickname, number) values (?,?)', (nickname, number))
        except sqlite3.IntegrityError as e:
            raise SMS900InvalidAddressbookEntry("%s or %s already added (probably: %s)" % (nickname, number, e))
        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def add_email(self, nickname, email):
        nickname = self._get_valid_nickname(nickname)
        email = self._get_valid_email(email)

        try:
            c = self.dbconn.cursor()
            c.execute('insert into phonebook_email(nickname, email) values (?, ?)', (nickname, email))
        except sqlite3.IntegrityError as e:
            raise SMS900InvalidAddressbookEntry("Email already added (probably: %s)" % (e))
        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def get_number(self, nickname):
        nickname = self._get_valid_nickname(nickname)

        try:
            c = self.dbconn.cursor()
            number = None
            for row in c.execute('select number from phonebook where nickname = ?', (nickname, )):
                number = row[0]

            if number:
                return number

            raise SMS900InvalidAddressbookEntry("nickname %s is not in my phone book" % nickname)

        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def get_nickname(self, number):
        try:
            c = self.dbconn.cursor()
            nickname = None
            for row in c.execute('select nickname from phonebook where number = ?', (number, )):
                nickname = row[0]

            if nickname:
                return nickname

            raise SMS900InvalidAddressbookEntry("number %s is not in my phone book" % number)

        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def get_nickname_from_email(self, email):
        try:
            c = self.dbconn.cursor()
            c.execute('select nickname from phonebook_email where email = ?', (email, ))
            result = c.fetchone()

            if result:
                return result[0]

            raise SMS900InvalidAddressbookEntry("The email %s is not in my phone book" % email)

        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def del_entry(self, nickname):
        nickname = self._get_valid_nickname(nickname)

        # Assume that the entry exists if this function is called
        try:
            c = self.dbconn.cursor()
            c.execute("delete from phonebook where nickname = ?", (nickname, ))
        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)

    def del_email(self, email):
        email = self._get_valid_email(email)

        try:
            c = self.dbconn.cursor()
            c.execute("delete from phonebook_email where email = ?", (email, ))
        except Exception as e:
            raise SMS900InvalidAddressbookEntry(e)


    def _get_valid_nickname(self, nickname):
        re_nickname = r'^([a-zA-Z][a-zA-Z0-9{}[\]\\`^-]{0,15})$'
        m = re.match(re_nickname, nickname)
        if not m:
            raise SMS900InvalidAddressbookEntry(
                f"Invalid nickname: {nickname} (Should match {re_nickname})"
            )

        return m.group(1).lower()

    def _get_valid_email(self, email):
        re_email = '.+@.+'
        m = re.match(re_email, email)
        if not m:
            raise SMS900InvalidAddressbookEntry(
                "Invalid email: %s (Should match %s)" % (email, re_email)
            )

        return email
