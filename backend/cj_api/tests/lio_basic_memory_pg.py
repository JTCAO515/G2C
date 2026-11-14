"""Actual native manual source -> indexed legacy intake/basic replies, local PG."""
from lio_cross_language_pg import main as shared_main

def main():shared_main(basic_memory=True)

if __name__=='__main__':main()
