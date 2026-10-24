// Create SIX separate Blank Queries with these names and expressions.
// ReadCsv function and ExportFolder parameter must exist first.
// Data type 'number' allows null aggregate counts; keys stay text.
// Avoid automatic relationship detection; create documented 1:* links manually.

// Query: DimProvider
ReadCsv("dim_provider.csv", {
    {"provider_code", type text}, {"provider_name", type text},
    {"region_name", type text}
})

// Query: DimSpecialty
ReadCsv("dim_specialty.csv", {
    {"specialty_code", type text}, {"specialty_name", type text},
    {"specialty_group", type text}
})

// Query: DimDate
ReadCsv("dim_date.csv", {
    {"reporting_month", type date}, {"month_key", type text},
    {"financial_year", type text}, {"quarter", type text}
})

// Query: FactRTT
ReadCsv("fact_rtt.csv", {
    {"provider_code", type text}, {"specialty_code", type text},
    {"reporting_month", type date}, {"data_source_type", type text},
    {"total_incomplete_pathways", type number}, {"within_18_weeks", type number},
    {"over_52_weeks", type number}, {"completed_pathways", type number}
})

// Query: FactPriority
ReadCsv("fact_priority.csv", {
    {"provider_code", type text}, {"specialty_code", type text},
    {"reporting_month", type date}, {"data_source_type", type text},
    {"priority_score", type number}, {"priority_band", type text},
    {"is_rankable", type logical}
})

// Query: BuildMetadata
ReadCsv("warehouse_metadata.csv", {
    {"built_at", type text}, {"data_source_type", type text},
    {"latest_reporting_month", type text}, {"fact_rows", Int64.Type},
    {"quality_score", type number}, {"referral_to_treatment_benchmark", type number}
})
