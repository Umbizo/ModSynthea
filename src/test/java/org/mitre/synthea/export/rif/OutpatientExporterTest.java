package org.mitre.synthea.export.rif;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.nio.file.Files;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.BeforeClass;
import org.junit.ClassRule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.mitre.synthea.TestHelper;
import org.mitre.synthea.helpers.Config;
import org.mitre.synthea.helpers.SimpleCSV;
import org.mitre.synthea.world.agents.PayerManager;
import org.mitre.synthea.world.agents.Person;
import org.mitre.synthea.world.agents.Provider;
import org.mitre.synthea.world.concepts.HealthRecord;
import org.mitre.synthea.world.concepts.HealthRecord.Code;
import org.mitre.synthea.world.concepts.HealthRecord.Encounter;
import org.mitre.synthea.world.concepts.HealthRecord.EncounterType;
import org.mitre.synthea.world.concepts.HealthRecord.Medication;
import org.mitre.synthea.world.geography.Location;

public class OutpatientExporterTest {

  private static final String TEST_BENE_ID = "TEST-NDC-LEAK";

  @ClassRule
  public static TemporaryFolder tempFolder = new TemporaryFolder();

  private static File exportDir;

  /**
   * Global setup for outpatient export tests.
   * @throws Exception if something goes wrong
   */
  @BeforeClass
  public static void setUpExportDir() throws Exception {
    TestHelper.exportOff();
    TestHelper.loadTestProperties();
    PayerManager.loadPayers(new Location("Massachusetts", null));
    Config.set("exporter.bfd.export", "true");
    Config.set("exporter.bfd.require_code_maps", "false");
    exportDir = tempFolder.newFolder();
    Config.set("exporter.baseDirectory", exportDir.toString());
    BB2RIFExporter.getInstance().prepareOutputFiles();
  }

  @Test
  public void unmappableMedicationDoesNotInheritPreviousLineNdc() throws Exception {
    long time = 1600000000000L; // Sep 2020, after the BFD claim cutoff date
    Person person = new Person(0L);
    person.attributes.put(Person.BIRTHDATE, time);
    person.attributes.put(RIFExporter.BB2_BENE_ID, TEST_BENE_ID);
    person.attributes.put(RIFExporter.COVERAGE_START_DATE, 0L);
    person.coverage.setPlanToNoInsurance(time);

    Provider provider = TestHelper.buildMockProvider();
    provider.state = "Massachusetts";
    HealthRecord record = person.record;
    Encounter encounter = record.encounterStart(time, EncounterType.OUTPATIENT);
    encounter.provider = provider;
    encounter.clinician = provider.clinicianMap.values().iterator().next().get(0);
    encounter.reason = new Code("SNOMED-CT", "44054006", "Type 2 diabetes mellitus");

    // First medication maps to an NDC via medication_code_map.json
    Medication withNdc = record.medicationAdministration(time, "860975");
    withNdc.codes.add(new Code("RxNorm", "860975", "metformin ER 500mg"));
    withNdc.claim.assignCosts();

    // Second medication is unmappable; its line must not inherit the first line's NDC
    Medication withoutNdc = record.medicationAdministration(time + 1, "999999");
    withoutNdc.codes.add(new Code("RxNorm", "999999", "unmappable test drug"));
    withoutNdc.claim.assignCosts();

    encounter.stop = time + 3600000L;
    encounter.ended = true;

    OutpatientExporter outpatientExporter =
        new OutpatientExporter(BB2RIFExporter.getInstance());
    long claimCount = outpatientExporter.export(person, 0L, encounter.stop);
    assertEquals(1, claimCount);

    // Exporter.appendToFile buffers output; flush so the file can be read back
    java.lang.reflect.Method closeOpenFiles =
        org.mitre.synthea.export.Exporter.class.getDeclaredMethod("closeOpenFiles");
    closeOpenFiles.setAccessible(true);
    closeOpenFiles.invoke(null);

    File outpatientFile = exportDir.toPath().resolve("bfd").resolve("outpatient.csv").toFile();
    assertTrue(outpatientFile.exists() && outpatientFile.isFile());
    String csvData = new String(Files.readAllBytes(outpatientFile.toPath()));
    List<LinkedHashMap<String, String>> rows = SimpleCSV.parse(csvData, '|').stream()
        .filter(row -> TEST_BENE_ID.equals(row.get("BENE_ID")))
        .collect(Collectors.toList());
    // two medication lines plus the total charge line
    assertEquals(3, rows.size());

    LinkedHashMap<String, String> mappableLine = rows.get(0);
    LinkedHashMap<String, String> unmappableLine = rows.get(1);
    assertFalse("mappable medication line should carry an NDC",
        mappableLine.get("REV_CNTR_IDE_NDC_UPC_NUM").isEmpty());
    assertEquals("unmappable medication line must not inherit the previous line's NDC",
        "", unmappableLine.get("REV_CNTR_IDE_NDC_UPC_NUM"));
  }
}
