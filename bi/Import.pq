// Power BI Desktop: create a text parameter named ExportFolder, ending
// with a slash or backslash, pointing to the completed bi/export directory.
// Create a Blank Query named ReadCsv and paste this function into Advanced Editor.
// CSV column names are fixed by scripts/export_bi.py.
(FileName as text, Types as list) as table =>
let
    Source = Csv.Document(
        File.Contents(ExportFolder & FileName),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Blanks = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),
    Dates = if Table.HasColumns(Blanks, "reporting_month") then
        Table.TransformColumns(Blanks, {{"reporting_month", each Date.FromText(_, [Format="yyyy-MM-dd", Culture="en-GB"]), type date}})
        else Blanks,
    Logicals = if Table.HasColumns(Dates, "is_rankable") then
        Table.TransformColumns(Dates, {{"is_rankable", each Logical.FromText(_), type logical}})
        else Dates,
    Typed = Table.TransformColumnTypes(Logicals, Types, "en-GB")
in
    Typed
