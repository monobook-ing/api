
Command-line Options:

--clean-db - Clean database before running tests
--debug - Enable verbose debug output
--help - Show usage information

# Run with clean database and debug output
./e2e_test.sh --clean-db --debug

# Run without database cleanup
./e2e_test.sh --debug

# Run normally (no debug output)
./e2e_test.sh --clean-db
