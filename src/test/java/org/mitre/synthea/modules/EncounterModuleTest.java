package org.mitre.synthea.modules;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertNotNull;

import org.junit.BeforeClass;
import org.junit.Test;
import org.mitre.synthea.TestHelper;
import org.mitre.synthea.helpers.Config;
import org.mitre.synthea.world.agents.PayerManager;
import org.mitre.synthea.world.agents.Person;
import org.mitre.synthea.world.agents.Provider;
import org.mitre.synthea.world.agents.ProviderTest;
import org.mitre.synthea.world.concepts.ClinicianSpecialty;
import org.mitre.synthea.world.concepts.HealthRecord.Encounter;
import org.mitre.synthea.world.concepts.HealthRecord.EncounterType;
import org.mitre.synthea.world.geography.Location;

public class EncounterModuleTest {

  private static Location location;
  private static Person person;
  private static EncounterModule module;

  /**
   * Setup the Encounter Module Tests.
   * @throws Exception on configuration loading error
   */
  @BeforeClass
  public static void setup() throws Exception {
    person = new Person(0L);
    // Give person an income to prevent null pointer.
    person.attributes.put(Person.INCOME, 100000);
    person.attributes.put(Person.BIRTHDATE, 0L);
    TestHelper.loadTestProperties();
    String testState = Config.get("test_state.default", "Massachusetts");
    location = new Location(testState, null);
    location.assignPoint(person, location.randomCityName(person));
    Provider.loadProviders(location, ProviderTest.providerRandom);
    module = new EncounterModule();
    // Ensure Person's Payer is not null.
    String testStateDefault = Config.get("test_state.default", "Massachusetts");
    PayerManager.loadPayers(new Location(testStateDefault, null));
    person.coverage.setPlanToNoInsurance((long) person.attributes.get(Person.BIRTHDATE));
    person.coverage.setPlanToNoInsurance(System.currentTimeMillis()
        + Config.getAsLong("generate.timestep"));
  }

  @Test
  public void testEncounterHasClinician() {
    module.process(person, System.currentTimeMillis());
    assertNotNull(person.record);
    assertFalse(person.record.encounters.isEmpty());
    int last = person.record.encounters.size() - 1;
    Encounter encounter = person.record.encounters.get(last);
    assertNotNull("Encounter must have clinician", encounter.clinician);
    assertNotNull("Encounter must have provider organization", encounter.provider);
  }

  @Test
  public void testEmergencySymptomEncounterHasClinician() {
    person.setSymptom(
        "Test", "Test", "Test", System.currentTimeMillis(),
        EncounterModule.EMERGENCY_SYMPTOM_THRESHOLD + 1, false
    );
    module.process(person, System.currentTimeMillis());
    assertNotNull(person.record);
    assertFalse(person.record.encounters.isEmpty());
    int last = person.record.encounters.size() - 1;
    Encounter encounter = person.record.encounters.get(last);
    assertNotNull("Encounter must have clinician", encounter.clinician);
    assertNotNull("Encounter must have provider organization", encounter.provider);
  }

  @Test
  public void testUrgentcareSymptomEncounterHasClinician() {
    person.setSymptom(
        "Test", "Test", "Test", System.currentTimeMillis(),
        EncounterModule.URGENT_CARE_SYMPTOM_THRESHOLD + 1, false
    );
    module.process(person, System.currentTimeMillis());
    assertNotNull(person.record);
    assertFalse(person.record.encounters.isEmpty());
    int last = person.record.encounters.size() - 1;
    Encounter encounter = person.record.encounters.get(last);
    assertNotNull("Encounter must have clinician", encounter.clinician);
    assertNotNull("Encounter must have provider organization", encounter.provider);
  }

  @Test
  public void testPrimarySymptomEncounterHasClinician() {
    person.setSymptom(
        "Test", "Test", "Test", System.currentTimeMillis(),
        EncounterModule.PCP_SYMPTOM_THRESHOLD + 1, false
    );
    module.process(person, System.currentTimeMillis());
    assertNotNull(person.record);
    assertFalse(person.record.encounters.isEmpty());
    int last = person.record.encounters.size() - 1;
    Encounter encounter = person.record.encounters.get(last);
    assertNotNull("Encounter must have clinician", encounter.clinician);
    assertNotNull("Encounter must have provider organization", encounter.provider);
  }

  @Test
  public void testCardiologyEncounterDoesNotAssignVeteranProviderToNonVeteran() {
    // Regression test: EncounterModule.createEncounter used to special-case cardiology
    // specialty encounters by assigning Provider.getProviderList().get(0) (arbitrary
    // HashMap iteration order) instead of the person's normal preferred provider. In
    // practice that first-in-the-list provider is a VETERAN (VA) facility, which is an
    // impossible/invalid assignment for a person who is not a veteran, and which also
    // caused RIFExporter.isVAorIHS() to suppress the encounter's RIF claims entirely.
    Person nonVeteran = new Person(2L);
    nonVeteran.attributes.put(Person.INCOME, 100000);
    nonVeteran.attributes.put(Person.BIRTHDATE, 0L);
    nonVeteran.attributes.remove(Person.VETERAN);
    location.assignPoint(nonVeteran, location.randomCityName(nonVeteran));
    nonVeteran.coverage.setPlanToNoInsurance((long) nonVeteran.attributes.get(Person.BIRTHDATE));
    nonVeteran.coverage.setPlanToNoInsurance(System.currentTimeMillis()
        + Config.getAsLong("generate.timestep"));

    Encounter encounter = EncounterModule.createEncounter(nonVeteran,
        System.currentTimeMillis(), EncounterType.AMBULATORY, ClinicianSpecialty.CARDIOLOGY,
        null, "EncounterModuleTest");

    assertNotNull("Cardiology encounter must have a provider organization", encounter.provider);
    assertNotEquals(
        "A non-veteran patient's cardiology encounter must not be assigned a VETERAN provider",
        Provider.ProviderType.VETERAN, encounter.provider.type);
  }

  @Test
  public void testDontStartNewEncounterIfExisting() {
    person.setSymptom(
        "Test", "Test", "Test", System.currentTimeMillis(),
        EncounterModule.EMERGENCY_SYMPTOM_THRESHOLD + 1, false
    );
    module.process(person, System.currentTimeMillis());
    assertNotNull(person.record);
    assertFalse(person.record.encounters.isEmpty());
    int numberOfEncounters = person.record.encounters.size();
    person.setSymptom(
        "Test", "Test", "Test", System.currentTimeMillis(),
        EncounterModule.EMERGENCY_SYMPTOM_THRESHOLD + 1, false
    );
    module.process(person, System.currentTimeMillis());
    assertEquals(numberOfEncounters, person.record.encounters.size());
  }
}
