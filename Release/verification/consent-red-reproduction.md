# Overwrite regression RED reproduction

These two tests were appended to the existing `PdfExportVerifierTest.cpp` fixture at source HEAD `f532d4838784b8178d3da909f5d5dc978f20395f`, before implementation changes. The fixture supplies `dir`, `expectation()` and a real Cairo `pdf(path, pages)` writer. Build `test-units`, then run:

```sh
./build/test/test-units '--gtest_filter=PdfExportVerifierTest.Gui*'
```

Both failed, with `published=true` and the other owner's contents replaced by the actual generated PDF. Full native failure output is in `consent-red.log`. The lasting tests use the new destination snapshot API captured before the competing file change; the old bool overload has been removed.

```cpp
TEST_F(PdfExportVerifierTest, GuiNewNameMustNotOverwriteFileCreatedBeforeWorkerStarts) {
    const auto output = dir / "new-name.pdf";
    ASSERT_FALSE(fs::exists(output));
    std::ofstream(output) << "late owner";
    auto result = PdfExportVerifier::exportChecked(
        output, expectation(), [&](const fs::path& p) { pdf(p, 3); }, [] { return false; }, true);
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(result.published);
    std::ifstream file(output);
    EXPECT_EQ(std::string((std::istreambuf_iterator<char>(file)), {}), "late owner");
}
TEST_F(PdfExportVerifierTest, GuiApprovalMustNotAuthorizeReplacementBeforeWorkerStarts) {
    const auto output = dir / "approved.pdf";
    std::ofstream(output) << "approved owner";
    fs::remove(output);
    std::ofstream(output) << "unapproved replacement";
    auto result = PdfExportVerifier::exportChecked(
        output, expectation(), [&](const fs::path& p) { pdf(p, 3); }, [] { return false; }, true);
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(result.published);
    std::ifstream file(output);
    EXPECT_EQ(std::string((std::istreambuf_iterator<char>(file)), {}), "unapproved replacement");
}
```
