-- Non-destructive migration for Android guardian-managed user profiles.
-- Existing ElderlyUsers rows, GuardianUserLinks, and ExerciseRecords are preserved.

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'gender') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD gender NVARCHAR(20) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'birth_date') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD birth_date DATE NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'height_cm') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD height_cm DECIMAL(5,2) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'weight_kg') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD weight_kg DECIMAL(5,2) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'health_condition') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD health_condition NVARCHAR(500) NULL;
END
GO
